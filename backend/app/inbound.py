"""What happens when a ticket arrives from a real channel, and when an agent answers one.

Same flow for every channel (email now, WhatsApp next):
  triage -> save -> auto-reply on the same channel
                 or acknowledge the student + alert senior support, and wait for an agent.
"""
import logging
import re

from . import db, email_channel
from .config import SENIOR_SUPPORT_EMAIL
from .graph import SAFETY_REPLY
from .triage import triage

log = logging.getLogger("inbound")

TEAM_NAMES = {
    "billing": "Billing", "academic_ops": "Academic Operations", "tech_support": "Tech Support",
    "mentors": "Subject Mentor", "senior_support": "Senior Support", "support": "Support",
}


def student_text(reply: str, ticket_id: int, citations: list[dict], passages: list[dict]) -> str:
    """Outbound version of a reply: no [n] markers, plus the help articles it was based on."""
    body = re.sub(r"\s*\[\d+\]", "", reply).strip()
    titles = {p["id"]: p["title"] for p in passages}
    used = list(dict.fromkeys(titles.get(c["passage_id"]) for c in citations if titles.get(c["passage_id"])))
    if used:
        body += "\n\nHelp articles:\n" + "\n".join(f"- {t}" for t in used)
    return f"{body}\n\nTicket #{ticket_id} · EduPrime Support (AI-assisted reply)"


def acknowledgement(ticket_id: int, team: str | None, self_harm: bool) -> str:
    if self_harm:
        return f"{SAFETY_REPLY}\n\nTicket #{ticket_id} · EduPrime Support"
    return (
        "Thank you for contacting EduPrime support. We've received your message and passed it to our "
        f"{TEAM_NAMES.get(team or 'support', 'Support')} team. A specialist will get back to you within 48 hours."
        f"\n\nTicket #{ticket_id} · EduPrime Support"
    )


def _send(channel: str, meta: dict, body: str) -> None:
    if channel == "email":
        email_channel.send_email(meta["contact"], meta.get("subject", "Your EduPrime query"), body,
                                 in_reply_to=meta.get("message_id"), references=meta.get("references"))
    else:
        raise ValueError(f"no outbound sender for channel {channel!r}")


def _deliver(ticket_id: int, channel: str, meta: dict, kind: str, body: str, to: str | None = None) -> bool:
    """Send and log the outcome on the ticket. A failed send is recorded, never raised: the ticket still exists."""
    to = to or meta.get("contact")
    try:
        if kind == "senior_alert":
            email_channel.send_alert(to, *body.split("\n", 1))
        else:
            _send(channel, meta, body)
        db.add_delivery(ticket_id, {"kind": kind, "channel": "email" if kind == "senior_alert" else channel,
                                    "to": to, "ok": True})
        return True
    except Exception as e:
        log.warning("delivery %s for ticket %s failed: %s", kind, ticket_id, e)
        db.add_delivery(ticket_id, {"kind": kind, "channel": channel, "to": to, "ok": False,
                                    "error": f"{type(e).__name__}: {e}"[:300]})
        return False


def senior_alert(ticket: dict) -> str:
    r = ticket["result"]
    urgent = r["decision"]["team"] == "senior_support"
    draft = (r.get("draft") or {}).get("reply", "")
    reasons = "\n".join(f"- {x}" for x in r["decision"]["reasons"])
    subject = f"{'[URGENT] ' if urgent else ''}Ticket #{ticket['id']} needs a human: {TEAM_NAMES.get(ticket['team'] or 'support')}"
    return (
        f"{subject}\n"
        f"From: {ticket['meta'].get('contact')} via {ticket['channel']}\n"
        f"Categories: {', '.join(ticket['categories']) or '-'} · sentiment: {ticket['sentiment'] or '-'}\n\n"
        f"Why it was escalated:\n{reasons}\n\n"
        f"Student wrote:\n{ticket['text']}\n\n"
        f"Suggested draft (review before sending):\n{draft}\n\n"
        f"Open the Inbox to edit and send the reply."
    )


def process_incoming(channel: str, item: dict) -> dict:
    """Triage a message from a real channel and act on the decision."""
    meta = {k: v for k, v in item.items() if k != "text"}
    result = triage(item["text"], channel)
    saved = db.save_result(result, meta=meta)
    ticket = db.get_ticket(saved.id)

    if result.decision.decision == "auto_reply" and result.draft:
        body = student_text(result.draft.reply, saved.id, ticket["result"]["citation_checks"], ticket["result"]["passages"])
        if not _deliver(saved.id, channel, meta, "auto_reply", body):
            # The student got nothing: put it in front of a human instead of showing "auto-replied".
            db.set_status(saved.id, "send_failed")
    else:
        self_harm = "self_harm" in result.precheck.flags
        _deliver(saved.id, channel, meta, "acknowledgement", acknowledgement(saved.id, result.decision.team, self_harm))
        if SENIOR_SUPPORT_EMAIL and email_channel.enabled():
            _deliver(saved.id, channel, meta, "senior_alert", senior_alert(db.get_ticket(saved.id)), to=SENIOR_SUPPORT_EMAIL)
    return db.get_ticket(saved.id)


def send_agent_reply(ticket: dict, reply: str) -> None:
    """When an agent approves a reply in the Inbox, send it to the student on their channel."""
    meta = ticket.get("meta") or {}
    if ticket["channel"] in {"email"} and meta.get("contact"):
        body = student_text(reply, ticket["id"], ticket["result"]["citation_checks"], ticket["result"]["passages"])
        if not _deliver(ticket["id"], ticket["channel"], meta, "agent_reply", body):
            db.set_status(ticket["id"], "send_failed")

"""Email channel: poll a Gmail inbox over IMAP, reply over SMTP in the same thread.

Needs EMAIL_ADDRESS and EMAIL_APP_PASSWORD (a Gmail App Password, not the account password).
Polling needs no public URL, so this works on a laptop as well as when deployed.
"""
import email
import html
import imaplib
import logging
import re
import smtplib
import threading
import time
from email.message import EmailMessage
from email.policy import default as default_policy
from email.utils import make_msgid, parseaddr

from .config import (
    EMAIL_ADDRESS, EMAIL_APP_PASSWORD, EMAIL_POLL_SECONDS, IMAP_HOST, SMTP_HOST, SMTP_PORT,
)

log = logging.getLogger("email_channel")

MAX_PER_POLL = 10
# Never reply to machines: prevents mail loops with auto-responders and bounces.
NO_REPLY_SENDER = re.compile(r"mailer-daemon|postmaster|no-?reply|donotreply|notifications?@", re.I)
QUOTED_REPLY = re.compile(r"(\n\s*On .{0,300}?wrote:\s*\n|\n-{2,}\s*Original Message\s*-{2,}|\n_{5,}\s*\nFrom:)", re.S | re.I)

status = {"enabled": False, "address": None, "last_poll": None, "last_error": None, "processed": 0}


def enabled() -> bool:
    return bool(EMAIL_ADDRESS and EMAIL_APP_PASSWORD)


def _html_to_text(s: str) -> str:
    s = re.sub(r"(?is)<(script|style).*?</\1>", "", s)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</div>", "\n", s)
    return html.unescape(re.sub(r"<[^>]+>", "", s))


def clean_body(body: str) -> str:
    """Keep only the new message: drop quoted earlier messages and '>' lines."""
    body = body.replace("\r\n", "\n")
    m = QUOTED_REPLY.search("\n" + body)
    if m:
        body = ("\n" + body)[: m.start()]
    lines = [ln for ln in body.split("\n") if not ln.lstrip().startswith(">")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def parse_message(raw: bytes) -> dict | None:
    """Turn a raw email into {contact, name, subject, message_id, references, text}, or None to skip it."""
    msg = email.message_from_bytes(raw, policy=default_policy)
    name, addr = parseaddr(msg.get("From", ""))
    addr = addr.lower()
    if not addr or addr == (EMAIL_ADDRESS or "").lower() or NO_REPLY_SENDER.search(addr):
        return None
    if msg.get("Auto-Submitted", "no").lower() != "no" or msg.get("Precedence", "").lower() in {"bulk", "list", "junk"}:
        return None

    part = msg.get_body(preferencelist=("plain", "html"))
    content = part.get_content() if part else ""
    if part is not None and part.get_content_type() == "text/html":
        content = _html_to_text(content)
    body = clean_body(content)
    subject = str(msg.get("Subject", "")).strip()
    # The subject often carries the issue ("Refund not received"), so give the classifier both.
    plain_subject = re.sub(r"^(re|fwd?):\s*", "", subject, flags=re.I).strip()
    text = f"{plain_subject}\n\n{body}".strip() if plain_subject and plain_subject.lower() not in body.lower() else body
    if not text:
        return None
    return {
        "contact": addr, "name": name, "subject": subject or "(no subject)",
        "message_id": msg.get("Message-ID"), "references": msg.get("References"), "text": text[:4000],
    }


def fetch_unseen() -> list[dict]:
    """Fetch unread emails (fetching marks them read, so each is processed once)."""
    out = []
    with imaplib.IMAP4_SSL(IMAP_HOST) as imap:
        imap.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
        imap.select("INBOX")
        _, data = imap.search(None, "UNSEEN")
        for num in data[0].split()[:MAX_PER_POLL]:
            _, msg_data = imap.fetch(num, "(RFC822)")
            parsed = parse_message(msg_data[0][1])
            if parsed:
                out.append(parsed)
    return out


def send_email(to: str, subject: str, body: str, in_reply_to: str | None = None, references: str | None = None) -> None:
    msg = EmailMessage()
    msg["From"] = f"EduPrime Support <{EMAIL_ADDRESS}>"
    msg["To"] = to
    msg["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    msg["Message-ID"] = make_msgid(domain=EMAIL_ADDRESS.split("@")[-1])
    msg["Auto-Submitted"] = "auto-replied"  # tells other auto-responders not to answer us
    if in_reply_to:  # keeps the reply in the student's existing thread
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = f"{references} {in_reply_to}".strip() if references else in_reply_to
    msg.set_content(body)
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
        smtp.send_message(msg)


def send_alert(to: str, subject: str, body: str) -> None:
    """A fresh email (not a reply), used for senior-support alerts."""
    msg = EmailMessage()
    msg["From"] = f"EduPrime Triage Bot <{EMAIL_ADDRESS}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg["Auto-Submitted"] = "auto-generated"
    msg.set_content(body)
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
        smtp.send_message(msg)


def _poll_forever(handle) -> None:
    while True:
        try:
            for item in fetch_unseen():
                handle(item)
                status["processed"] += 1
            status["last_error"] = None
        except Exception as e:  # network blips, bad credentials: report and keep polling
            status["last_error"] = f"{type(e).__name__}: {e}"[:300]
            log.warning("email poll failed: %s", status["last_error"])
        status["last_poll"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        time.sleep(EMAIL_POLL_SECONDS)


def start_poller(handle) -> bool:
    if not enabled():
        return False
    status.update(enabled=True, address=EMAIL_ADDRESS)
    threading.Thread(target=_poll_forever, args=(handle,), daemon=True, name="email-poller").start()
    return True

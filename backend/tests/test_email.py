"""Email channel tests: parsing, loop prevention, and the inbound flow with fake senders (no network)."""
import importlib
from email.message import EmailMessage

import pytest

from app import email_channel, inbound
from app.schemas import Citation, Classification, Draft, EscalationDecision, PrecheckResult, TriageResult

SUPPORT = "eduprime.support.demo@gmail.com"


def raw_email(frm="Riya <riya@example.com>", subject="Refund status", body="When will my refund come?",
              html=None, headers=None) -> bytes:
    m = EmailMessage()
    m["From"], m["To"], m["Subject"], m["Message-ID"] = frm, SUPPORT, subject, "<abc123@example.com>"
    for k, v in (headers or {}).items():
        m[k] = v
    m.set_content(body)
    if html:
        m.add_alternative(html, subtype="html")
    return m.as_bytes()


@pytest.fixture(autouse=True)
def support_address(monkeypatch):
    monkeypatch.setattr(email_channel, "EMAIL_ADDRESS", SUPPORT)


# ---------- parsing ----------

def test_parse_plain_email():
    p = email_channel.parse_message(raw_email())
    assert p["contact"] == "riya@example.com" and p["name"] == "Riya"
    assert p["message_id"] == "<abc123@example.com>"
    assert p["text"] == "Refund status\n\nWhen will my refund come?"


def test_subject_not_repeated_when_body_contains_it():
    p = email_channel.parse_message(raw_email(subject="Re: OTP", body="OTP not coming on my phone"))
    assert p["text"] == "OTP not coming on my phone"


def test_quoted_previous_message_is_dropped():
    body = "Still not received.\n\nOn Mon, 5 Oct 2026 at 10:00, EduPrime Support <x@y.com> wrote:\n> Your refund..."
    assert email_channel.parse_message(raw_email(body=body))["text"].endswith("Still not received.")


@pytest.mark.parametrize("signature", [
    "\nSent from my iPhone", "\n\nSent from my Galaxy", "\n-- \nShubham Raj\n+91 98xxxxxx", "\nGet Outlook for Android",
])
def test_signatures_are_stripped(signature):
    p = email_channel.parse_message(raw_email(subject="Query for PW", body="Any course left for GATE CSE 2027 ?" + signature))
    assert p["text"] == "Query for PW\n\nAny course left for GATE CSE 2027 ?"


def test_body_mentioning_sent_from_mid_text_is_kept():
    body = "I paid via the link sent from my bank app.\nStill no access."
    assert email_channel.parse_message(raw_email(subject="x", body=body))["text"].endswith("Still no access.")


def test_html_only_email():
    m = EmailMessage()
    m["From"], m["Subject"] = "a@b.com", "Help"
    m.set_content("<p>Video <b>not</b> playing</p>", subtype="html")
    assert "Video not playing" in email_channel.parse_message(m.as_bytes())["text"]


@pytest.mark.parametrize("frm,headers", [
    (SUPPORT, None),                                  # our own outgoing mail
    ("Mail Delivery <mailer-daemon@google.com>", None),  # bounce
    ("no-reply@bank.com", None),
    ("riya@example.com", {"Auto-Submitted": "auto-replied"}),  # someone's out-of-office
    ("list@example.com", {"Precedence": "bulk"}),
])
def test_machine_mail_is_ignored(frm, headers):
    assert email_channel.parse_message(raw_email(frm=frm, headers=headers)) is None


# ---------- inbound flow ----------

def fake_result(decision: str, team=None, flags=()):
    cls = Classification(categories=["refund"], confidence=0.9, sentiment="calm", at_risk=False,
                         requires_human_action=decision == "escalate", language="en", issues=["refund timeline"],
                         search_query="refund")
    from app.kb import get_kb
    p = get_kb().by_id["refund_policy#refund-timelines"]
    quote = p.text.split(". ")[0]
    draft = Draft(reply="Your refund arrives in 5-7 working days [1].",
                  citations=[Citation(marker=1, passage_id=p.id, quote=quote)], kb_sufficient=True)
    from app.citations import verify_citations
    return TriageResult(ticket_text="When will my refund come?", channel="email",
                        precheck=PrecheckResult(flags=list(flags)), classification=cls, passages=[p], draft=draft,
                        citation_checks=verify_citations(draft, get_kb()),
                        decision=EscalationDecision(decision=decision, team=team, reasons=["x"]))


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.db"))
    import app.config, app.db
    importlib.reload(app.config)
    importlib.reload(app.db)
    monkeypatch.setattr(app.db, "seed_if_empty", lambda: None)
    app.db.init_db()
    monkeypatch.setattr(inbound, "db", app.db)
    sent, alerts = [], []
    monkeypatch.setattr(email_channel, "send_email", lambda to, subj, body, **kw: sent.append((to, subj, body, kw)))
    monkeypatch.setattr(email_channel, "send_alert", lambda to, subj, body: alerts.append((to, subj, body)))
    monkeypatch.setattr(email_channel, "enabled", lambda: True)
    monkeypatch.setattr(inbound, "SENIOR_SUPPORT_EMAIL", "senior@eduprime.test")
    return sent, alerts


ITEM = {"contact": "riya@example.com", "name": "Riya", "subject": "Refund status",
        "message_id": "<abc123@example.com>", "references": None, "text": "When will my refund come?"}


def test_auto_reply_is_sent_in_thread_without_markers(env, monkeypatch):
    sent, alerts = env
    monkeypatch.setattr(inbound, "triage", lambda text, ch: fake_result("auto_reply"))
    t = inbound.process_incoming("email", ITEM)
    to, subj, body, kw = sent[0]
    assert to == "riya@example.com" and kw["in_reply_to"] == "<abc123@example.com>"
    assert "[1]" not in body and "5-7 working days" in body
    assert "Refund Policy > Refund timelines" in body and f"Ticket #{t['id']}" in body
    assert alerts == [] and t["status"] == "auto_sent"
    assert t["meta"]["deliveries"][0]["kind"] == "auto_reply" and t["meta"]["deliveries"][0]["ok"]


def test_escalation_acknowledges_student_and_alerts_senior(env, monkeypatch):
    sent, alerts = env
    monkeypatch.setattr(inbound, "triage", lambda text, ch: fake_result("escalate", team="senior_support"))
    t = inbound.process_incoming("email", ITEM)
    assert "Senior Support team" in sent[0][2] and "5-7 working days" not in sent[0][2]  # draft not sent
    to, subj, body = alerts[0]
    assert to == "senior@eduprime.test" and subj.startswith("[URGENT] Ticket #")
    assert "riya@example.com" in body and "Your refund arrives" in body  # draft included for the agent
    assert [d["kind"] for d in t["meta"]["deliveries"]] == ["acknowledgement", "senior_alert"]
    assert t["status"] == "pending_review"


def test_self_harm_acknowledgement_has_helpline(env, monkeypatch):
    sent, _ = env
    monkeypatch.setattr(inbound, "triage", lambda text, ch: fake_result("escalate", "senior_support", ["self_harm"]))
    inbound.process_incoming("email", ITEM)
    assert "14416" in sent[0][2]


def test_failed_send_is_logged_not_raised(env, monkeypatch):
    def boom(*a, **k):
        raise OSError("SMTP down")
    monkeypatch.setattr(email_channel, "send_email", boom)
    monkeypatch.setattr(inbound, "triage", lambda text, ch: fake_result("auto_reply"))
    t = inbound.process_incoming("email", ITEM)
    d = t["meta"]["deliveries"][0]
    assert d["ok"] is False and "SMTP down" in d["error"]


def test_agent_reply_goes_to_student(env, monkeypatch):
    sent, _ = env
    monkeypatch.setattr(inbound, "triage", lambda text, ch: fake_result("escalate", team="billing"))
    t = inbound.process_incoming("email", ITEM)
    inbound.send_agent_reply(inbound.db.get_ticket(t["id"]), "Your refund was approved today [1].")
    assert sent[-1][0] == "riya@example.com" and "approved today" in sent[-1][2] and "[1]" not in sent[-1][2]


def test_form_tickets_send_nothing(env):
    sent, _ = env
    inbound.send_agent_reply({"id": 1, "channel": "form", "meta": {}, "result": {}}, "hi")
    assert sent == []

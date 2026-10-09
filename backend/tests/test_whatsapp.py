"""WhatsApp (Twilio) channel tests: signature check, webhook, background triage, replies. No network."""
import base64
import hashlib
import hmac
import importlib

import pytest
from fastapi.testclient import TestClient

from app import inbound, whatsapp_channel
from tests.test_email import fake_result

TOKEN = "test-auth-token"
URL = "http://testserver/api/whatsapp/webhook"


def sign(url: str, params: dict) -> str:
    payload = url + "".join(k + params[k] for k in sorted(params))
    return base64.b64encode(hmac.new(TOKEN.encode(), payload.encode(), hashlib.sha1).digest()).decode()


@pytest.fixture(autouse=True)
def twilio_creds(monkeypatch):
    monkeypatch.setattr(whatsapp_channel, "TWILIO_ACCOUNT_SID", "ACtest")
    monkeypatch.setattr(whatsapp_channel, "TWILIO_AUTH_TOKEN", TOKEN)
    monkeypatch.setattr(whatsapp_channel, "_seen", {})


def msg(body="Video buffer ho rahi hai", sid="SM1"):
    return {"From": "whatsapp:+919876543210", "To": "whatsapp:+14155238886", "Body": body,
            "ProfileName": "Riya", "MessageSid": sid}


# ---------- unit ----------

def test_signature_matches_twilio_scheme():
    p = msg()
    assert whatsapp_channel.valid_signature(URL, p, sign(URL, p))
    assert not whatsapp_channel.valid_signature(URL, p, sign(URL, {**p, "Body": "tampered"}))
    assert not whatsapp_channel.valid_signature(URL, p, "")


def test_parse_webhook():
    item = whatsapp_channel.parse_webhook(msg())
    assert item == {"contact": "+919876543210", "name": "Riya", "message_sid": "SM1", "text": "Video buffer ho rahi hai"}
    assert whatsapp_channel.parse_webhook({**msg(), "Body": "  "}) is None          # media-only
    assert whatsapp_channel.parse_webhook({**msg(), "From": "+919876543210"}) is None  # not WhatsApp


def test_duplicate_message_sid():
    assert not whatsapp_channel.is_duplicate("SM9")
    assert whatsapp_channel.is_duplicate("SM9")


def test_send_whatsapp_calls_twilio(monkeypatch):
    calls = []

    class R:
        status_code, text = 201, "{}"

    monkeypatch.setattr(whatsapp_channel.httpx, "post", lambda url, **kw: calls.append((url, kw)) or R())
    whatsapp_channel.send_whatsapp("+919876543210", "x" * 2000)
    url, kw = calls[0]
    assert url.endswith("/Accounts/ACtest/Messages.json") and kw["auth"] == ("ACtest", TOKEN)
    assert kw["data"]["To"] == "whatsapp:+919876543210" and len(kw["data"]["Body"]) == 1600


# ---------- webhook through the app ----------

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "w.db"))
    import app.config, app.db, app.main
    importlib.reload(app.config)
    importlib.reload(app.db)
    monkeypatch.setattr(app.db, "seed_if_empty", lambda: None)
    importlib.reload(app.main)
    monkeypatch.setattr(app.main.email_channel, "start_poller", lambda handle: False)
    monkeypatch.setattr(inbound, "db", app.db)
    sent = []
    monkeypatch.setattr(whatsapp_channel, "send_whatsapp", lambda to, body: sent.append((to, body)))
    monkeypatch.setattr(inbound.email_channel, "enabled", lambda: False)  # no senior email in these tests
    with TestClient(app.main.app) as c:
        c.sent = sent
        yield c


def post(client, params, signature=None):
    return client.post("/api/whatsapp/webhook", data=params,
                       headers={"X-Twilio-Signature": signature if signature is not None else sign(URL, params)})


def test_forged_request_is_rejected(client, monkeypatch):
    monkeypatch.setattr(inbound, "triage", lambda t, ch: pytest.fail("must not triage a forged request"))
    assert post(client, msg(), signature="forged").status_code == 403
    assert client.sent == []


def test_message_is_triaged_and_answered_on_whatsapp(client, monkeypatch):
    monkeypatch.setattr(inbound, "triage", lambda t, ch: fake_result("auto_reply"))
    r = post(client, msg())
    assert r.status_code == 200 and r.text == "<Response></Response>"
    to, body = client.sent[0]
    assert to == "+919876543210" and "5-7 working days" in body and "[1]" not in body
    t = client.get("/api/tickets").json()[0]
    assert t["channel"] == "whatsapp" and t["meta"]["contact"] == "+919876543210" and t["status"] == "auto_sent"


def test_twilio_retry_does_not_create_second_ticket(client, monkeypatch):
    monkeypatch.setattr(inbound, "triage", lambda t, ch: fake_result("auto_reply"))
    post(client, msg(sid="SM42"))
    post(client, msg(sid="SM42"))
    assert len(client.get("/api/tickets").json()) == 1 and len(client.sent) == 1


def test_escalation_acknowledges_on_whatsapp_and_agent_reply_goes_there(client, monkeypatch):
    monkeypatch.setattr(inbound, "triage", lambda t, ch: fake_result("escalate", team="billing"))
    post(client, msg(body="Refund chahiye, order EP-55120"))
    assert "Billing team" in client.sent[0][1]
    t = client.get("/api/tickets").json()[0]
    assert t["status"] == "pending_review"
    client.post(f"/api/tickets/{t['id']}/resolve", json={"reply": "Your refund is approved [1]."})
    assert client.sent[-1][0] == "+919876543210" and "approved" in client.sent[-1][1]


def test_webhook_404_when_not_configured(client, monkeypatch):
    monkeypatch.setattr(whatsapp_channel, "TWILIO_ACCOUNT_SID", "")
    assert post(client, msg()).status_code == 404

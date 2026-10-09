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
    assert item == {"contact": "+919876543210", "name": "Riya", "message_sid": "SM1",
                    "our_number": "whatsapp:+14155238886", "text": "Video buffer ho rahi hai"}
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
    whatsapp_channel.send_whatsapp("+919876543210", "x" * 2000, from_number="whatsapp:+17372508034")
    url, kw = calls[0]
    assert kw["data"]["From"] == "whatsapp:+17372508034"
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
    monkeypatch.setattr(whatsapp_channel, "send_whatsapp", lambda to, body, from_number=None: sent.append((to, body, from_number)))
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


def test_fast_reply_comes_back_in_the_webhook_response(client, monkeypatch):
    monkeypatch.setattr(inbound, "triage", lambda t, ch: fake_result("auto_reply"))
    r = post(client, msg())
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/xml")
    assert "<Message>" in r.text and "5-7 working days" in r.text and "[1]" not in r.text
    assert client.sent == []  # answered in the HTTP response, no separate API send needed
    t = client.get("/api/tickets").json()[0]
    assert t["channel"] == "whatsapp" and t["meta"]["contact"] == "+919876543210" and t["status"] == "auto_sent"
    assert t["meta"]["deliveries"][0]["via"] == "webhook reply"


def test_slow_triage_sends_holding_message_then_api_reply(client, monkeypatch):
    import time
    import app.main
    monkeypatch.setattr(app.main, "WEBHOOK_REPLY_BUDGET_S", 0.2)

    def slow(t, ch):
        time.sleep(0.6)
        return fake_result("auto_reply")
    monkeypatch.setattr(inbound, "triage", slow)
    r = post(client, msg(sid="SMslow"))
    assert "looking into it" in r.text
    for _ in range(40):  # the pipeline keeps running after the webhook answered
        if client.sent:
            break
        time.sleep(0.05)
    to, body, from_number = client.sent[0]
    assert to == "+919876543210" and "5-7 working days" in body
    assert from_number == "whatsapp:+14155238886"  # replies come from the number the student wrote to


def test_twilio_retry_does_not_create_second_ticket(client, monkeypatch):
    monkeypatch.setattr(inbound, "triage", lambda t, ch: fake_result("auto_reply"))
    first, second = post(client, msg(sid="SM42")), post(client, msg(sid="SM42"))
    assert "<Message>" in first.text and "<Message>" not in second.text
    assert len(client.get("/api/tickets").json()) == 1


def test_escalation_acknowledges_on_whatsapp_and_agent_reply_goes_there(client, monkeypatch):
    monkeypatch.setattr(inbound, "triage", lambda t, ch: fake_result("escalate", team="billing"))
    r = post(client, msg(body="Refund chahiye, order EP-55120"))
    assert "Billing team" in r.text
    t = client.get("/api/tickets").json()[0]
    assert t["status"] == "pending_review"
    client.post(f"/api/tickets/{t['id']}/resolve", json={"reply": "Your refund is approved [1]."})
    assert client.sent[-1][0] == "+919876543210" and "approved" in client.sent[-1][1]


def test_twiml_escapes_reply():
    assert "&lt;b&gt; &amp;" in whatsapp_channel.twiml("<b> &")
    assert whatsapp_channel.twiml(None).endswith("<Response></Response>")


def test_webhook_404_when_not_configured(client, monkeypatch):
    monkeypatch.setattr(whatsapp_channel, "TWILIO_ACCOUNT_SID", "")
    assert post(client, msg()).status_code == 404

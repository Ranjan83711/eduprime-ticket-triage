"""Meta WhatsApp Cloud API channel tests: handshake, signature, parsing, replies. No network."""
import hashlib
import hmac
import importlib
import json

import pytest
from fastapi.testclient import TestClient

from app import inbound, meta_whatsapp
from tests.test_email import fake_result

SECRET, VERIFY = "app-secret", "verify-me"


@pytest.fixture(autouse=True)
def meta_creds(monkeypatch):
    for k, v in {"META_WA_TOKEN": "tok", "META_WA_PHONE_NUMBER_ID": "123", "META_APP_SECRET": SECRET,
                 "META_WA_VERIFY_TOKEN": VERIFY}.items():
        monkeypatch.setattr(meta_whatsapp, k, v)
    monkeypatch.setattr(meta_whatsapp, "_seen", {})


def payload(text="Video buffer ho rahi hai", mid="wamid.1", statuses=False):
    value = {"messaging_product": "whatsapp", "contacts": [{"wa_id": "919876543210", "profile": {"name": "Riya"}}]}
    if statuses:
        value["statuses"] = [{"id": "wamid.x", "status": "delivered"}]
    else:
        value["messages"] = [{"from": "919876543210", "id": mid, "type": "text", "text": {"body": text}}]
    return {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "messages", "value": value}]}]}


def signed(body: dict) -> tuple[bytes, str]:
    raw = json.dumps(body).encode()
    return raw, "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()


def test_parse_text_message():
    assert meta_whatsapp.parse_webhook(payload()) == [
        {"contact": "+919876543210", "name": "Riya", "message_id": "wamid.1", "provider": "meta",
         "text": "Video buffer ho rahi hai"}]
    assert meta_whatsapp.parse_webhook(payload(statuses=True)) == []


def test_send_text_calls_graph_api(monkeypatch):
    calls = []

    class R:
        status_code, text = 200, "{}"

    monkeypatch.setattr(meta_whatsapp.httpx, "post", lambda url, **kw: calls.append((url, kw)) or R())
    meta_whatsapp.send_text("+919876543210", "hello")
    url, kw = calls[0]
    assert url.endswith("/123/messages") and kw["headers"]["Authorization"] == "Bearer tok"
    assert kw["json"] == {"messaging_product": "whatsapp", "to": "919876543210", "type": "text", "text": {"body": "hello"}}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "m.db"))
    import app.config, app.db, app.main
    importlib.reload(app.config)
    importlib.reload(app.db)
    monkeypatch.setattr(app.db, "seed_if_empty", lambda: None)
    importlib.reload(app.main)
    monkeypatch.setattr(app.main.email_channel, "start_poller", lambda handle: False)
    monkeypatch.setattr(inbound, "db", app.db)
    monkeypatch.setattr(inbound.email_channel, "enabled", lambda: False)
    sent = []
    monkeypatch.setattr(meta_whatsapp, "send_text", lambda to, body: sent.append((to, body)))
    with TestClient(app.main.app) as c:
        c.sent = sent
        yield c


def test_verification_handshake(client):
    ok = client.get("/api/whatsapp/meta-webhook", params={"hub.mode": "subscribe", "hub.verify_token": VERIFY, "hub.challenge": "42"})
    assert ok.status_code == 200 and ok.text == "42"
    bad = client.get("/api/whatsapp/meta-webhook", params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "42"})
    assert bad.status_code == 403


def test_forged_post_rejected(client, monkeypatch):
    monkeypatch.setattr(inbound, "triage", lambda t, ch: pytest.fail("must not triage a forged request"))
    raw, _ = signed(payload())
    r = client.post("/api/whatsapp/meta-webhook", content=raw, headers={"X-Hub-Signature-256": "sha256=forged",
                                                                        "Content-Type": "application/json"})
    assert r.status_code == 403 and client.sent == []


def post(client, body):
    raw, sig = signed(body)
    return client.post("/api/whatsapp/meta-webhook", content=raw,
                       headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})


def test_message_answered_via_meta(client, monkeypatch):
    monkeypatch.setattr(inbound, "triage", lambda t, ch: fake_result("auto_reply"))
    assert post(client, payload()).status_code == 200
    to, body = client.sent[0]
    assert to == "+919876543210" and "5-7 working days" in body and "[1]" not in body
    t = client.get("/api/tickets").json()[0]
    assert t["channel"] == "whatsapp" and t["meta"]["provider"] == "meta" and t["status"] == "auto_sent"


def test_status_updates_and_retries_ignored(client, monkeypatch):
    monkeypatch.setattr(inbound, "triage", lambda t, ch: fake_result("auto_reply"))
    post(client, payload(statuses=True))
    post(client, payload(mid="wamid.7"))
    post(client, payload(mid="wamid.7"))
    assert len(client.get("/api/tickets").json()) == 1 and len(client.sent) == 1


def test_agent_reply_goes_out_via_meta(client, monkeypatch):
    monkeypatch.setattr(inbound, "triage", lambda t, ch: fake_result("escalate", team="billing"))
    post(client, payload(text="Refund chahiye", mid="wamid.9"))
    assert "Billing team" in client.sent[0][1]
    t = client.get("/api/tickets").json()[0]
    client.post(f"/api/tickets/{t['id']}/resolve", json={"reply": "Your refund is approved [1]."})
    assert client.sent[-1] == ("+919876543210", client.sent[-1][1]) and "approved" in client.sent[-1][1]

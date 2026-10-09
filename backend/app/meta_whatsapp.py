"""WhatsApp channel via Meta's official WhatsApp Cloud API.

Meta verifies the webhook once (GET with hub.verify_token), then POSTs JSON for each message, signed
with the app secret in X-Hub-Signature-256. Replies are sent with the Graph API; free-form text is
allowed within 24 h of the student's last message, so no templates are needed for replies.
Uses plain httpx (no SDK).
"""
import hashlib
import hmac
import time

import httpx

from .config import META_APP_SECRET, META_GRAPH_VERSION, META_WA_PHONE_NUMBER_ID, META_WA_TOKEN, META_WA_VERIFY_TOKEN

MAX_LEN = 4096  # WhatsApp text message limit
status = {"enabled": False, "received": 0, "last_error": None}
_seen: dict[str, float] = {}  # message id -> time; Meta retries deliveries it thinks failed


def enabled() -> bool:
    return bool(META_WA_TOKEN and META_WA_PHONE_NUMBER_ID and META_APP_SECRET and META_WA_VERIFY_TOKEN)


def init_status() -> None:
    status["enabled"] = enabled()


def verify_subscription(mode: str | None, token: str | None, challenge: str | None) -> str | None:
    """The one-time GET handshake when the webhook is saved in Meta's dashboard."""
    if mode == "subscribe" and token and hmac.compare_digest(token, META_WA_VERIFY_TOKEN) and challenge:
        return challenge
    return None


def valid_signature(raw_body: bytes, header: str) -> bool:
    expected = "sha256=" + hmac.new(META_APP_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header or "")


def is_duplicate(message_id: str) -> bool:
    now = time.time()
    for mid, t in list(_seen.items()):
        if now - t > 3600:
            del _seen[mid]
    if message_id in _seen:
        return True
    _seen[message_id] = now
    return False


def parse_webhook(payload: dict) -> list[dict]:
    """Meta's nested JSON -> channel-neutral items. Status updates and non-text messages are skipped."""
    items = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            names = {c.get("wa_id"): c.get("profile", {}).get("name") for c in value.get("contacts", [])}
            for msg in value.get("messages", []):
                text = (msg.get("text", {}).get("body") or "").strip() if msg.get("type") == "text" else ""
                if not text:
                    continue
                items.append({"contact": "+" + msg["from"], "name": names.get(msg["from"]),
                              "message_id": msg.get("id"), "provider": "meta", "text": text[:4000]})
    return items


def send_text(to: str, body: str) -> None:
    if len(body) > MAX_LEN:
        body = body[: MAX_LEN - 1] + "…"
    r = httpx.post(f"https://graph.facebook.com/{META_GRAPH_VERSION}/{META_WA_PHONE_NUMBER_ID}/messages",
                   headers={"Authorization": f"Bearer {META_WA_TOKEN}"}, timeout=20,
                   json={"messaging_product": "whatsapp", "to": to.lstrip("+"), "type": "text", "text": {"body": body}})
    if r.status_code >= 300:
        raise RuntimeError(f"Meta send failed: {r.status_code} {r.text[:250]}")

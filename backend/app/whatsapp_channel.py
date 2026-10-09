"""WhatsApp channel via Twilio: a webhook receives messages, the REST API sends replies.

Twilio calls our webhook with form fields (From, Body, ProfileName, MessageSid) and signs each request
with the account's auth token, so we verify X-Twilio-Signature before trusting anything. Twilio waits
only ~15 s for the webhook, so the app acknowledges at once and triages in the background.
Uses plain httpx (no Twilio SDK needed).
"""
import base64
import hashlib
import hmac
import time
from xml.sax.saxutils import escape

import httpx

from .config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM

MAX_LEN = 1600  # Twilio's limit for one WhatsApp message body
status = {"enabled": False, "from": None, "received": 0, "last_error": None}
_seen: dict[str, float] = {}  # MessageSid -> time; Twilio retries a webhook it thinks timed out


def enabled() -> bool:
    return bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN)


def init_status() -> None:
    status.update(enabled=enabled(), **{"from": TWILIO_WHATSAPP_FROM if enabled() else None})


def valid_signature(url: str, params: dict, signature: str) -> bool:
    """Twilio's scheme: HMAC-SHA1 over the full URL + each POST param name and value, sorted by name."""
    payload = url + "".join(k + params[k] for k in sorted(params))
    digest = hmac.new(TWILIO_AUTH_TOKEN.encode(), payload.encode(), hashlib.sha1).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), signature or "")


def is_duplicate(message_sid: str) -> bool:
    now = time.time()
    for sid, t in list(_seen.items()):
        if now - t > 3600:
            del _seen[sid]
    if message_sid in _seen:
        return True
    _seen[message_sid] = now
    return False


def parse_webhook(params: dict) -> dict | None:
    """Twilio form fields -> the channel-neutral item the inbound flow expects, or None to ignore."""
    text = (params.get("Body") or "").strip()
    sender = params.get("From", "")
    if not text or not sender.startswith("whatsapp:"):
        return None  # media-only messages, status callbacks, non-WhatsApp
    # "To" is our number the student wrote to; replies go out from that same number.
    return {"contact": sender.removeprefix("whatsapp:"), "name": params.get("ProfileName") or None,
            "message_sid": params.get("MessageSid"), "our_number": params.get("To") or None, "text": text[:4000]}


def send_whatsapp(to: str, body: str, from_number: str | None = None) -> None:
    """Reply from the number the student messaged (from_number); TWILIO_WHATSAPP_FROM is the fallback."""
    to = to if to.startswith("whatsapp:") else f"whatsapp:{to}"
    if len(body) > MAX_LEN:
        body = body[: MAX_LEN - 1] + "…"
    r = httpx.post(f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json",
                   auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN), timeout=20,
                   data={"From": from_number or TWILIO_WHATSAPP_FROM, "To": to, "Body": body})
    if r.status_code >= 300:
        raise RuntimeError(f"Twilio send failed: {r.status_code} {r.text[:200]}")


def twiml(reply: str | None) -> str:
    """Webhook response: reply in the same HTTP response (a TwiML <Message>), or empty."""
    if not reply:
        return '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
    if len(reply) > MAX_LEN:
        reply = reply[: MAX_LEN - 1] + "…"
    return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escape(reply)}</Message></Response>'

"""Shared test setup: tests never use real credentials or talk to real services, whatever is in .env."""
import pytest

from app import email_channel, meta_whatsapp, whatsapp_channel


@pytest.fixture(autouse=True)
def no_real_credentials(monkeypatch):
    for name in ("GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN", "EMAIL_APP_PASSWORD"):
        monkeypatch.setattr(email_channel, name, "")
    monkeypatch.setattr(email_channel, "_token", {"value": None, "expires": 0.0})
    for name in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN"):
        monkeypatch.setattr(whatsapp_channel, name, "")
    for name in ("META_WA_TOKEN", "META_WA_PHONE_NUMBER_ID", "META_APP_SECRET", "META_WA_VERIFY_TOKEN"):
        monkeypatch.setattr(meta_whatsapp, name, "")
    # Any HTTP call that a test forgot to fake fails loudly instead of reaching the internet.
    def blocked(*args, **kwargs):
        raise AssertionError(f"test tried a real HTTP call: {args[:1]}")
    monkeypatch.setattr(email_channel.httpx, "post", blocked)

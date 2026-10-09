"""Central settings. Everything tunable lives here and can be overridden via .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
load_dotenv(ROOT_DIR / ".env")

# Only trace to LangSmith when a key is configured; otherwise tracing just logs errors.
if not os.getenv("LANGSMITH_API_KEY"):
    os.environ["LANGSMITH_TRACING"] = "false"

DATA_DIR = BACKEND_DIR / "data"
KB_DIR = DATA_DIR / "kb"
TEST_SET_PATH = DATA_DIR / "tickets" / "test_set.json"
CACHE_DIR = Path(os.getenv("CACHE_DIR", BACKEND_DIR / ".cache"))
DB_PATH = Path(os.getenv("DB_PATH", BACKEND_DIR / "triage.db"))

# Models: Flash-Lite for both steps, and a model on a different provider as fallback when Gemini
# rate-limits. gemini-3.5-flash was tried for drafting but its free tier allows only 20 requests/day,
# so most drafts silently fell back to Groq; Flash-Lite already produced 100% verified citations.
CLASSIFIER_MODEL = os.getenv("CLASSIFIER_MODEL", "gemini-3.5-flash-lite")
DRAFTER_MODEL = os.getenv("DRAFTER_MODEL", "gemini-3.5-flash-lite")
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "openai/gpt-oss-120b")

# Below this classifier confidence the ticket goes to a human.
AUTO_REPLY_CONFIDENCE = float(os.getenv("AUTO_REPLY_CONFIDENCE", "0.7"))

# Retrieval
TOP_K_PASSAGES = int(os.getenv("TOP_K_PASSAGES", "4"))

# USD per 1M tokens (input, output), used to report cost per ticket.
# Free tier costs nothing; these are paid standard-tier list prices (checked Oct 2026) so we can
# report what production would cost. Longest prefix first: "gemini-3.5-flash" would match the lite model.
MODEL_PRICES = {
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.5-flash": (1.50, 9.00),
    "openai/gpt-oss-120b": (0.15, 0.75),
}

PROMPT_VERSION = "v5"

# Email channel (Gmail IMAP/SMTP). Disabled unless both are set.
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS", "").strip()
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD", "").replace(" ", "")  # Google shows it with spaces
IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
EMAIL_POLL_SECONDS = int(os.getenv("EMAIL_POLL_SECONDS", "30"))
# Optional: send through the Gmail API (HTTPS) instead of SMTP. Needed on hosts that block SMTP
# ports, such as Render's free tier. Get the refresh token once with `python -m scripts.gmail_auth`.
GMAIL_CLIENT_ID = os.getenv("GMAIL_CLIENT_ID", "").strip()
GMAIL_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET", "").strip()
GMAIL_REFRESH_TOKEN = os.getenv("GMAIL_REFRESH_TOKEN", "").strip()
# WhatsApp channel via Twilio (sandbox for the demo). Disabled unless SID and token are set.
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886").strip()
# WhatsApp channel via Meta's WhatsApp Cloud API (preferred when configured).
META_WA_TOKEN = os.getenv("META_WA_TOKEN", "").strip()
META_WA_PHONE_NUMBER_ID = os.getenv("META_WA_PHONE_NUMBER_ID", "").strip()
META_APP_SECRET = os.getenv("META_APP_SECRET", "").strip()
META_WA_VERIFY_TOKEN = os.getenv("META_WA_VERIFY_TOKEN", "").strip()  # any string; must match Meta's webhook setting
META_GRAPH_VERSION = os.getenv("META_GRAPH_VERSION", "v25.0").strip()
# Where "a human is needed" alerts go.
SENIOR_SUPPORT_EMAIL = os.getenv("SENIOR_SUPPORT_EMAIL", "").strip()

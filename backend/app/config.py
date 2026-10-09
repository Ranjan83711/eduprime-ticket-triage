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
CACHE_DIR = BACKEND_DIR / ".cache"
DB_PATH = Path(os.getenv("DB_PATH", BACKEND_DIR / "triage.db"))

# Models: a small fast model for classification, a stronger one for writing replies,
# and a model on a different provider as fallback when Gemini rate-limits.
CLASSIFIER_MODEL = os.getenv("CLASSIFIER_MODEL", "gemini-2.5-flash-lite")
DRAFTER_MODEL = os.getenv("DRAFTER_MODEL", "gemini-2.5-flash")
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "llama-3.3-70b-versatile")

# Below this classifier confidence the ticket goes to a human.
AUTO_REPLY_CONFIDENCE = float(os.getenv("AUTO_REPLY_CONFIDENCE", "0.7"))

# Retrieval
TOP_K_PASSAGES = int(os.getenv("TOP_K_PASSAGES", "4"))

# USD per 1M tokens (input, output), used to report cost per ticket.
# Free tier costs nothing; these are the paid-tier list prices for reference.
MODEL_PRICES = {
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
    "llama-3.3-70b-versatile": (0.59, 0.79),
}

PROMPT_VERSION = "v1"

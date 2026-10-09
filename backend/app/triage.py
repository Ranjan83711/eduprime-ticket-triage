"""Public entry point: run the graph for one ticket, with a disk cache.

The cache key includes the models and prompt version, so changing either invalidates it.
Caching keeps repeated demo clicks and eval reruns inside the free-tier quota.
"""
import hashlib
import json

from .config import CACHE_DIR, CLASSIFIER_MODEL, DRAFTER_MODEL, FALLBACK_MODEL, PROMPT_VERSION
from .graph import run_graph
from .schemas import TriageResult


def _cache_key(text: str, channel: str) -> str:
    raw = json.dumps([text.strip(), channel, CLASSIFIER_MODEL, DRAFTER_MODEL, FALLBACK_MODEL, PROMPT_VERSION])
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def triage(text: str, channel: str = "form", use_cache: bool = True) -> TriageResult:
    path = CACHE_DIR / f"{_cache_key(text, channel)}.json"
    if use_cache and path.exists():
        return TriageResult.model_validate_json(path.read_text(encoding="utf-8"))

    state, latency_ms = run_graph(text, channel)
    calls = state.get("llm_calls", [])
    result = TriageResult(
        ticket_text=text,
        channel=channel,
        precheck=state["precheck"],
        classification=state.get("classification"),
        passages=state.get("passages", []),
        draft=state.get("draft"),
        citation_checks=state.get("citation_checks", []),
        decision=state["decision"],
        llm_calls=calls,
        total_latency_ms=latency_ms,
        total_cost_usd=round(sum(c.cost_usd for c in calls), 6),
        error=state.get("error"),
    )
    # Don't cache failures, so a rate-limited run is retried next time.
    if use_cache and not result.error:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(result.model_dump_json(), encoding="utf-8")
    return result

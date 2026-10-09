"""LLM access: Gemini as primary, Groq as fallback, structured output, usage/cost accounting.

Every call goes through `call_structured`, which returns the parsed Pydantic object plus an
LLMCall record (model actually used, tokens, latency, cost), so we can report cost per ticket.
"""
import time
from functools import lru_cache

from langchain_core.messages import BaseMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from pydantic import BaseModel

from .config import CLASSIFIER_MODEL, DRAFTER_MODEL, FALLBACK_MODEL, MODEL_PRICES
from .schemas import LLMCall

TIMEOUT_S = 30


def _gemini(model: str) -> ChatGoogleGenerativeAI:
    # Minimal thinking: these are short, well-specified tasks; thinking added ~265 reasoning tokens and
    # ~1.5s per call without changing the output. Gemini 3 rejects thinking_budget=0, so use thinking_level.
    # Flash-Lite uses fixed sampling and warns if temperature is passed, so only set it for other models.
    # max_retries is low because the Groq fallback is faster than waiting out a rate limit.
    sampling = {} if "lite" in model else {"temperature": 0}
    return ChatGoogleGenerativeAI(model=model, max_retries=1, timeout=TIMEOUT_S,
                                  thinking_config={"thinking_level": "minimal"}, **sampling)


def _groq() -> ChatGroq:
    # gpt-oss is a reasoning model; low effort keeps latency and tokens down for these simple tasks.
    # Groq's free tier allows only 8k tokens/minute, so let its client wait out short rate limits.
    return ChatGroq(model_name=FALLBACK_MODEL, temperature=0, max_retries=3, request_timeout=TIMEOUT_S,
                    reasoning_effort="low")


def _is_rate_limit(e: Exception) -> bool:
    s = f"{type(e).__name__} {e}"
    return "429" in s or "RESOURCE_EXHAUSTED" in s or "RateLimit" in s


RATE_LIMIT_WAITS_S = (10, 25)  # both providers rate-limited: free-tier limits are per minute, so wait it out


@lru_cache(maxsize=None)
def structured_chain(role: str, schema: type[BaseModel]):
    """Primary Gemini model with structured output, falling back to Groq on any error (e.g. 429)."""
    model = CLASSIFIER_MODEL if role == "classifier" else DRAFTER_MODEL
    primary = _gemini(model).with_structured_output(schema, include_raw=True)
    fallback = _groq().with_structured_output(schema, include_raw=True)
    return primary.with_fallbacks([fallback])


def _cost(model: str, inp: int, out: int) -> float:
    for name, (pin, pout) in sorted(MODEL_PRICES.items(), key=lambda kv: -len(kv[0])):
        if model.startswith(name):
            return (inp * pin + out * pout) / 1_000_000
    return 0.0


def call_structured(step: str, role: str, schema: type[BaseModel], messages: list[BaseMessage]):
    start = time.perf_counter()
    for wait in (*RATE_LIMIT_WAITS_S, None):
        try:
            out = structured_chain(role, schema).invoke(messages)
            break
        except Exception as e:
            if wait is None or not _is_rate_limit(e):
                raise
            time.sleep(wait)
    latency_ms = int((time.perf_counter() - start) * 1000)

    raw = out["raw"]
    if out.get("parsing_error") or out.get("parsed") is None:
        raise ValueError(f"{step}: model output did not match schema: {out.get('parsing_error')}")

    usage = getattr(raw, "usage_metadata", None) or {}
    meta = getattr(raw, "response_metadata", {}) or {}
    model_name = meta.get("model_name") or meta.get("model") or ""
    fallback_used = not model_name.startswith("gemini")
    inp, outp = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
    return out["parsed"], LLMCall(
        step=step, model=model_name or "unknown", input_tokens=inp, output_tokens=outp,
        latency_ms=latency_ms, cost_usd=round(_cost(model_name, inp, outp), 6), fallback_used=fallback_used,
    )

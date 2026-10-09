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
    # thinking_budget=0: these are short, well-specified tasks; thinking adds latency and tokens
    # without measurably helping. max_retries is low because the Groq fallback is faster than waiting.
    return ChatGoogleGenerativeAI(model=model, temperature=0, max_retries=1, timeout=TIMEOUT_S, thinking_budget=0)


def _groq() -> ChatGroq:
    return ChatGroq(model_name=FALLBACK_MODEL, temperature=0, max_retries=1, request_timeout=TIMEOUT_S)


@lru_cache(maxsize=None)
def structured_chain(role: str, schema: type[BaseModel]):
    """Primary Gemini model with structured output, falling back to Groq on any error (e.g. 429)."""
    model = CLASSIFIER_MODEL if role == "classifier" else DRAFTER_MODEL
    primary = _gemini(model).with_structured_output(schema, include_raw=True)
    fallback = _groq().with_structured_output(schema, include_raw=True)
    return primary.with_fallbacks([fallback])


def _cost(model: str, inp: int, out: int) -> float:
    for name, (pin, pout) in MODEL_PRICES.items():
        if model.startswith(name):
            return (inp * pin + out * pout) / 1_000_000
    return 0.0


def call_structured(step: str, role: str, schema: type[BaseModel], messages: list[BaseMessage]):
    start = time.perf_counter()
    out = structured_chain(role, schema).invoke(messages)
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

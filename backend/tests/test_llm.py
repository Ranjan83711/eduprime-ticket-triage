"""Tests for the LLM wrapper's rate-limit retry and cost accounting (no network)."""
import pytest
from langchain_core.messages import AIMessage

from app import llm
from app.schemas import Classification


class FakeChain:
    def __init__(self, errors):
        self.errors, self.calls = list(errors), 0

    def invoke(self, messages):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        parsed = Classification(categories=["payment"], confidence=0.9, sentiment="calm", at_risk=False,
                                requires_human_action=False, language="en", issues=["x"], search_query="x")
        raw = AIMessage(content="", usage_metadata={"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100},
                        response_metadata={"model_name": "gemini-3.5-flash-lite"})
        return {"raw": raw, "parsed": parsed, "parsing_error": None}


@pytest.fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)


def use_chain(monkeypatch, chain):
    monkeypatch.setattr(llm, "structured_chain", lambda role, schema: chain)


def test_retries_on_rate_limit_then_succeeds(monkeypatch, no_sleep):
    chain = FakeChain([RuntimeError("429 RESOURCE_EXHAUSTED")])
    use_chain(monkeypatch, chain)
    parsed, call = llm.call_structured("classify", "classifier", Classification, [])
    assert chain.calls == 2 and parsed.categories == ["payment"]
    assert call.cost_usd == pytest.approx((1000 * 0.30 + 100 * 2.50) / 1e6)
    assert not call.fallback_used


def test_gives_up_after_retries(monkeypatch, no_sleep):
    chain = FakeChain([RuntimeError("429")] * 5)
    use_chain(monkeypatch, chain)
    with pytest.raises(RuntimeError):
        llm.call_structured("classify", "classifier", Classification, [])
    assert chain.calls == len(llm.RATE_LIMIT_WAITS_S) + 1


def test_other_errors_are_not_retried(monkeypatch, no_sleep):
    chain = FakeChain([ValueError("bad request")])
    use_chain(monkeypatch, chain)
    with pytest.raises(ValueError):
        llm.call_structured("classify", "classifier", Classification, [])
    assert chain.calls == 1


def test_cost_prefers_longest_model_prefix():
    assert llm._cost("gemini-3.5-flash-lite", 1_000_000, 0) == 0.30
    assert llm._cost("gemini-3.5-flash", 1_000_000, 0) == 1.50
    assert llm._cost("unknown-model", 1_000_000, 0) == 0.0

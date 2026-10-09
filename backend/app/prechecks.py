"""Deterministic checks that run before any LLM call.

These cover cases where we never want to depend on a model's judgement: safety concerns,
legal/chargeback threats and prompt-injection attempts. Regex is cheap, instant and auditable.
"""
import re

from .schemas import PrecheckResult

# flag name -> (pattern, critical). Critical flags skip the LLM entirely and go to a human.
RULES: dict[str, tuple[re.Pattern, bool]] = {
    "self_harm": (re.compile(
        r"giving up on life|give up on life|suicid|kill (my|him|her)self|end (my|his|her) life|"
        r"don'?t want to live|jaan de (dunga|dungi|denge)|mar (jaunga|jaungi|jaana)", re.I), True),
    "prompt_injection": (re.compile(
        r"ignore (all |any )?(the )?(previous|prior|above) instructions|disregard (all |the )?(previous|above)|"
        r"you are now|system prompt|authori[sz]ed by (the )?admin", re.I), True),
    "legal_threat": (re.compile(
        r"consumer (court|forum)|legal action|lawyer|advocate|sue you|police|\bFIR\b|legal notice", re.I), False),
    "chargeback_or_fraud": (re.compile(r"chargeback|charge back|\bfraud\b|scam|unauthori[sz]ed (charge|transaction)", re.I), False),
    "social_media_threat": (re.compile(r"twitter|\bx\.com\b|instagram|linkedin|youtube video|post (it|this|about this) (on|online)|viral", re.I), False),
}

ORDER_ID = re.compile(r"\bEP-\d{4,6}\b", re.I)
UTR = re.compile(r"\b\d{12}\b")


def run_prechecks(text: str) -> PrecheckResult:
    flags = [name for name, (pattern, _) in RULES.items() if pattern.search(text)]
    return PrecheckResult(
        flags=flags,
        critical=any(RULES[f][1] for f in flags),
        order_ids=[m.upper() for m in ORDER_ID.findall(text)],
        utr_numbers=UTR.findall(text),
    )

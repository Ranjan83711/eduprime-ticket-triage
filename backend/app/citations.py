"""Verifies that every citation in a drafted reply really comes from the knowledge base.

The LLM must copy an exact sentence from the passage it cites. We check that the passage id
exists and the quote appears in it (after normalising whitespace/punctuation, with a small fuzzy
tolerance), and that every [n] marker in the reply has a matching citation.
"""
import re
from difflib import SequenceMatcher

from .kb import KnowledgeBase
from .schemas import CitationCheck, Draft

FUZZY_THRESHOLD = 0.9


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text.lower())).strip()


def _quote_in_passage(quote: str, passage: str) -> bool:
    q, p = _norm(quote), _norm(passage)
    if not q:
        return False
    if q in p:
        return True
    # Allow small copy differences (e.g. "Rs." vs "Rs"): best match against a same-length window.
    m = SequenceMatcher(None, p, q, autojunk=False).find_longest_match(0, len(p), 0, len(q))
    start = max(0, m.a - m.b)
    return SequenceMatcher(None, p[start:start + len(q)], q).ratio() >= FUZZY_THRESHOLD


def verify_citations(draft: Draft, kb: KnowledgeBase) -> list[CitationCheck]:
    checks = []
    for c in draft.citations:
        passage = kb.by_id.get(c.passage_id)
        if passage is None:
            checks.append(CitationCheck(**c.model_dump(), valid=False, reason="unknown passage id"))
        elif not _quote_in_passage(c.quote, passage.text):
            checks.append(CitationCheck(**c.model_dump(), valid=False, reason="quote not found in passage"))
        else:
            checks.append(CitationCheck(**c.model_dump(), valid=True))

    cited = {c.marker for c in draft.citations}
    for marker in sorted({int(m) for m in re.findall(r"\[(\d+)\]", draft.reply)} - cited):
        checks.append(CitationCheck(marker=marker, passage_id="", quote="", valid=False,
                                    reason="marker in reply has no citation"))
    return checks

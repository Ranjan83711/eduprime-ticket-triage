"""Verifies that every citation in a drafted reply really comes from the knowledge base.

The LLM must copy an exact sentence from the passage it cites. We check that the passage id
exists and the quote appears in it (after normalising whitespace/punctuation, with a small fuzzy
tolerance), and that every [n] marker in the reply has a matching citation.
"""
import re
from difflib import SequenceMatcher

from .kb import KnowledgeBase, tokenize
from .schemas import CitationCheck, Draft

FUZZY_THRESHOLD = 0.9
DUPLICATE_OVERLAP = 0.5  # share of the shorter sentence's content words that must also be in the other


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


def strip_pasted_quotes(draft: Draft) -> Draft:
    """Remove citation quotes the model pasted into the reply on top of its own paraphrase.

    Flash-Lite sometimes writes "You can store 100 lectures [1]. A maximum of 100 lectures can be
    stored offline at a time. [1]". The prompt forbids it, but code makes it reliable. A quote is
    only removed if text remains, so a reply that is nothing but a quote is left alone.
    """
    reply = draft.reply
    for c in draft.citations:
        quote = c.quote.strip().rstrip(".")
        if len(quote) < 20:
            continue
        pattern = re.compile(re.escape(quote) + r"\.?[ \t]*(\[\d+\])?\.?")
        for m in reversed(list(pattern.finditer(reply))):
            before = reply[:m.start()].rstrip()
            # It's a duplicate only if the sentence right before it cites the same marker and says
            # the same thing. Otherwise the quote is the reply's only statement of that fact: keep it.
            if not before.rstrip(".").endswith(f"[{c.marker}]"):
                continue
            prev_sentence = re.split(r"(?<=[.!?])\s+", before.rstrip("."))[-1]
            a, b = set(tokenize(prev_sentence)), set(tokenize(quote))
            if a and b and len(a & b) / min(len(a), len(b)) >= DUPLICATE_OVERLAP:
                reply = (reply[:m.start()] + reply[m.end():]).strip()
                break
    reply = re.sub(r"[ \t]{2,}", " ", reply)
    return draft.model_copy(update={"reply": reply})


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

"""Knowledge base: markdown docs split into passages (one per '##' section), searched with BM25.

The KB is ~50 short passages, so keyword search is enough and avoids running an embedding
model or vector DB. Hinglish tickets are handled by searching with the classifier's English
`search_query` instead of the raw ticket text.
"""
import re
from functools import lru_cache
from pathlib import Path

from rank_bm25 import BM25Okapi

from .config import KB_DIR, TOP_K_PASSAGES
from .schemas import Passage

STOPWORDS = set(
    "a an the is are was were be been to of and or in on for with my me i you your it this that "
    "can could do does did how what when where why will would should have has had not no from at by "
    "as if so but please hi hello".split()
)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS]


def load_passages(kb_dir: Path = KB_DIR) -> list[Passage]:
    passages = []
    for path in sorted(kb_dir.glob("*.md")):
        doc_title, section, lines = path.stem, None, []
        for line in path.read_text(encoding="utf-8").splitlines() + ["## __end__"]:
            if line.startswith("# "):
                doc_title = line[2:].strip()
            elif line.startswith("## "):
                if section and lines:
                    passages.append(Passage(
                        id=f"{path.stem}#{_slug(section)}",
                        doc=path.stem,
                        title=f"{doc_title} > {section}",
                        text=" ".join(lines).strip(),
                    ))
                section, lines = line[3:].strip(), []
            elif line.strip():
                lines.append(line.strip())
    return passages


class KnowledgeBase:
    def __init__(self, passages: list[Passage]):
        self.passages = passages
        self.by_id = {p.id: p for p in passages}
        # Title words are indexed too, so "refund timeline" finds the "Refund timelines" section.
        self._bm25 = BM25Okapi([tokenize(p.title + " " + p.text) for p in passages])

    def search(self, query: str, k: int = TOP_K_PASSAGES) -> list[Passage]:
        tokens = tokenize(query)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        ranked = sorted(zip(scores, self.passages), key=lambda x: x[0], reverse=True)
        return [p.model_copy(update={"score": round(float(s), 3)}) for s, p in ranked[:k] if s > 0]

    def search_many(self, queries: list[str], k: int = TOP_K_PASSAGES) -> list[Passage]:
        """Search each issue separately and merge, so multi-issue tickets get passages for every issue."""
        best: dict[str, Passage] = {}
        for q in queries:
            for p in self.search(q, k=3):
                if p.id not in best or p.score > best[p.id].score:
                    best[p.id] = p
        return sorted(best.values(), key=lambda p: p.score, reverse=True)[: max(k, 2 * len(queries))]


@lru_cache(maxsize=1)
def get_kb() -> KnowledgeBase:
    return KnowledgeBase(load_passages())

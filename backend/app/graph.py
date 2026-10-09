"""The triage pipeline as a LangGraph state machine.

    precheck ──critical──────────────────────────────────────────┐
        │                                                        ▼
        └─► classify ─► retrieve ─► draft ─► verify ─► decide ─┬─► auto_reply ─► END
                                                               └─► escalate   ─► END

Critical pre-check flags (safety, prompt injection) skip the LLM entirely.
Any LLM failure is caught inside the node and the ticket is escalated instead of crashing.
"""
import time
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from . import prompts
from .citations import strip_pasted_quotes, verify_citations
from .escalation import decide
from .kb import get_kb
from .llm import call_structured
from .prechecks import run_prechecks
from .schemas import (
    CitationCheck, Classification, Draft, EscalationDecision, LLMCall, Passage, PrecheckResult,
)

SAFETY_REPLY = (
    "Thank you for reaching out, and we're really sorry you're going through this. Your message has been "
    "passed to a senior member of our team who will contact you personally as soon as possible. If you or "
    "someone you know needs to talk to someone right now, please call Tele-MANAS, India's free 24x7 mental "
    "health helpline, at 14416 or 1-800-891-4416."
)
HOLDING_REPLY = (
    "Thank you for contacting EduPrime support. Your request has been passed to a senior support specialist, "
    "who will get back to you within 48 hours."
)


class TriageState(TypedDict, total=False):
    ticket: str
    channel: str
    precheck: PrecheckResult
    classification: Classification | None
    passages: list[Passage]
    draft: Draft | None
    citation_checks: list[CitationCheck]
    decision: EscalationDecision
    llm_calls: list[LLMCall]
    error: str | None


def precheck_node(state: TriageState) -> TriageState:
    return {"precheck": run_prechecks(state["ticket"]), "llm_calls": [], "classification": None,
            "draft": None, "passages": [], "citation_checks": [], "error": None}


def classify_node(state: TriageState) -> TriageState:
    msgs = [SystemMessage(prompts.CLASSIFIER_SYSTEM),
            HumanMessage(prompts.CLASSIFIER_USER.format(channel=state["channel"], ticket=state["ticket"]))]
    try:
        cls, call = call_structured("classify", "classifier", Classification, msgs)
        if not cls.categories:
            cls.categories = ["other"]
        return {"classification": cls, "llm_calls": state["llm_calls"] + [call]}
    except Exception as e:  # both providers failed or bad output
        return {"error": f"classification failed: {type(e).__name__}: {e}"[:500]}


def retrieve_node(state: TriageState) -> TriageState:
    cls = state["classification"]
    queries = [cls.search_query] + cls.issues
    return {"passages": get_kb().search_many(queries)}


def draft_node(state: TriageState) -> TriageState:
    cls = state["classification"]
    msgs = [SystemMessage(prompts.DRAFTER_SYSTEM),
            HumanMessage(prompts.DRAFTER_USER.format(
                channel=state["channel"], ticket=state["ticket"], issues="; ".join(cls.issues),
                needs_action="yes" if cls.requires_human_action else "no",
                passages=prompts.format_passages(state["passages"])))]
    try:
        draft, call = call_structured("draft", "drafter", Draft, msgs)
        return {"draft": draft, "llm_calls": state["llm_calls"] + [call]}
    except Exception as e:
        return {"error": f"drafting failed: {type(e).__name__}: {e}"[:500]}


def verify_node(state: TriageState) -> TriageState:
    if state.get("draft") is None:
        return {"citation_checks": []}
    draft = strip_pasted_quotes(state["draft"])
    return {"draft": draft, "citation_checks": verify_citations(draft, get_kb())}


def decide_node(state: TriageState) -> TriageState:
    d = decide(state["precheck"], state.get("classification"), state.get("draft"), state.get("citation_checks", []))
    if state.get("error"):
        d.reasons.append(state["error"])
    return {"decision": d}


def auto_reply_node(state: TriageState) -> TriageState:
    return {}


def escalate_node(state: TriageState) -> TriageState:
    """Make sure an escalated ticket always has a safe holding reply for the human to send or edit."""
    if state.get("draft") is not None:
        return {}
    reply = SAFETY_REPLY if "self_harm" in state["precheck"].flags else HOLDING_REPLY
    return {"draft": Draft(reply=reply, citations=[], kb_sufficient=False)}


def build_graph():
    g = StateGraph(TriageState)
    for name, fn in [("precheck", precheck_node), ("classify", classify_node), ("retrieve", retrieve_node),
                     ("draft", draft_node), ("verify", verify_node), ("decide", decide_node),
                     ("auto_reply", auto_reply_node), ("escalate", escalate_node)]:
        g.add_node(name, fn)

    g.add_edge(START, "precheck")
    g.add_conditional_edges("precheck", lambda s: "decide" if s["precheck"].critical else "classify",
                            ["decide", "classify"])
    g.add_conditional_edges("classify", lambda s: "decide" if s.get("classification") is None else "retrieve",
                            ["decide", "retrieve"])
    g.add_edge("retrieve", "draft")
    g.add_edge("draft", "verify")
    g.add_edge("verify", "decide")
    g.add_conditional_edges("decide", lambda s: s["decision"].decision, {"auto_reply": "auto_reply",
                                                                          "escalate": "escalate"})
    g.add_edge("auto_reply", END)
    g.add_edge("escalate", END)
    return g.compile()


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def run_graph(ticket: str, channel: str = "form") -> tuple[TriageState, int]:
    start = time.perf_counter()
    state = get_graph().invoke({"ticket": ticket, "channel": channel},
                               config={"run_name": "ticket_triage", "tags": [channel]})
    return state, int((time.perf_counter() - start) * 1000)

"""Pydantic models shared by the pipeline, the API and the LLM structured outputs."""
from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["refund", "payment", "batch_access", "technical", "academic_doubt", "other"]
Sentiment = Literal["calm", "frustrated", "angry"]
Decision = Literal["auto_reply", "escalate"]
Team = Literal["billing", "academic_ops", "tech_support", "mentors", "senior_support", "support"]


# ---------- LLM structured outputs ----------

class Classification(BaseModel):
    """What the classifier LLM returns for a ticket."""

    categories: list[Category] = Field(
        description="All categories present in the ticket, most important first. Use more than one only "
        "if the student raises genuinely separate issues."
    )
    confidence: float = Field(
        ge=0, le=1,
        description="How sure you are about the categories, 0 to 1. Use below 0.6 if the ticket is vague or ambiguous.",
    )
    sentiment: Sentiment
    at_risk: bool = Field(
        description="True if the student threatens to leave, demands money back angrily, mentions social media, "
        "legal action or consumer court, or sounds distressed."
    )
    requires_human_action: bool = Field(
        description="True only if a staff member must do something in internal systems to resolve the ticket. "
        "False if a policy answer, a timeline, or self-serve steps resolve it. See the rules in the instructions."
    )
    language: Literal["en", "hi", "hinglish"]
    issues: list[str] = Field(
        description="Each distinct issue the student raises, as a short English phrase. Empty if the message "
        "raises no issue (a greeting, thanks, or 'my issue is resolved')."
    )
    search_query: str = Field(
        description="A short English search query to find the relevant help-centre policy (translate Hinglish/Hindi)."
    )


class Citation(BaseModel):
    marker: int = Field(description="The number used in the reply, e.g. 1 for [1].")
    passage_id: str = Field(description="The id of the knowledge base passage being cited.")
    quote: str = Field(description="An exact sentence copied word for word from that passage that supports the claim.")


class Draft(BaseModel):
    """What the drafter LLM returns."""

    reply: str = Field(description="The reply to the student with [n] citation markers after policy claims.")
    citations: list[Citation]
    kb_sufficient: bool = Field(
        description="False if the knowledge base passages do not contain what is needed to answer every issue."
    )


# ---------- Pipeline outputs ----------

class PrecheckResult(BaseModel):
    flags: list[str] = Field(default_factory=list)
    critical: bool = False
    order_ids: list[str] = Field(default_factory=list)
    utr_numbers: list[str] = Field(default_factory=list)


class Passage(BaseModel):
    id: str
    doc: str
    title: str
    text: str
    score: float = 0.0


class CitationCheck(BaseModel):
    marker: int
    passage_id: str
    quote: str
    valid: bool
    reason: str = ""


class EscalationDecision(BaseModel):
    decision: Decision
    team: Team | None = None
    reasons: list[str] = Field(default_factory=list)


class LLMCall(BaseModel):
    step: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    cost_usd: float = 0.0
    fallback_used: bool = False


class TriageResult(BaseModel):
    ticket_text: str
    channel: str = "form"
    precheck: PrecheckResult
    classification: Classification | None = None
    passages: list[Passage] = Field(default_factory=list)
    draft: Draft | None = None
    citation_checks: list[CitationCheck] = Field(default_factory=list)
    decision: EscalationDecision
    llm_calls: list[LLMCall] = Field(default_factory=list)
    total_latency_ms: int = 0
    total_cost_usd: float = 0.0
    error: str | None = None


class TicketIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    channel: Literal["email", "whatsapp", "form"] = "form"

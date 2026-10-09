"""The escalation rule: plain code, not an LLM decision, so it is predictable and testable.

A ticket is auto-replied only if NONE of these hold:
  1. A pre-check flag fired (safety, prompt injection, legal, chargeback/fraud, social media threat).
  2. The student is angry or at risk of churning.
  3. Resolving it needs a staff member to act in internal systems.
  4. It contains an academic doubt (mentors answer those, not support).
  5. Classifier confidence is below the threshold.
  6. The KB could not answer every issue, or any citation failed verification.
All reasons that apply are returned, so a human sees exactly why it was escalated.
"""
from .config import AUTO_REPLY_CONFIDENCE
from .schemas import CitationCheck, Classification, Draft, EscalationDecision, PrecheckResult

TEAM_BY_CATEGORY = {
    "refund": "billing",
    "payment": "billing",
    "batch_access": "academic_ops",
    "technical": "tech_support",
    "academic_doubt": "mentors",
    "other": "support",
}


def decide(
    precheck: PrecheckResult,
    classification: Classification | None,
    draft: Draft | None,
    citation_checks: list[CitationCheck],
    threshold: float = AUTO_REPLY_CONFIDENCE,
) -> EscalationDecision:
    reasons: list[str] = []
    senior = False

    for flag in precheck.flags:
        reasons.append(f"pre-check flag: {flag}")
        senior = True

    if classification is None:
        reasons.append("ticket was not classified")
        return EscalationDecision(decision="escalate", team="senior_support" if senior else "support", reasons=reasons)

    c = classification
    if c.sentiment == "angry":
        reasons.append("student is angry")
        senior = True
    if c.at_risk:
        reasons.append("student is at risk of churning")
        senior = True
    if c.requires_human_action:
        reasons.append("needs a staff member to act in internal systems")
    if "academic_doubt" in c.categories and c.requires_human_action:
        reasons.append("academic doubt goes to the mentor team")
    if c.confidence < threshold:
        reasons.append(f"classifier confidence {c.confidence:.2f} below threshold {threshold:.2f}")

    if draft is None:
        reasons.append("no reply was drafted")
    else:
        if not draft.kb_sufficient:
            reasons.append("knowledge base does not cover every issue")
        bad = [ch for ch in citation_checks if not ch.valid]
        if bad:
            reasons.append(f"{len(bad)} citation(s) failed verification")
        if not draft.citations:
            reasons.append("reply has no citations")

    if not reasons:
        return EscalationDecision(decision="auto_reply", reasons=["all checks passed"])

    team = "senior_support" if senior else TEAM_BY_CATEGORY[c.categories[0]] if c.categories else "support"
    return EscalationDecision(decision="escalate", team=team, reasons=reasons)

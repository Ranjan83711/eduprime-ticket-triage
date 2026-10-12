# Architecture Decision Log

Each entry: context → options → decision → trade-offs → status. Sources: code [V] and the development conversation [H].

---

### ADR-01: Problem #6 first, #1 later
- **Context:** the assignment allows one of six problems in ~3 days. [H]
- **Decision:** build #6 Support Ticket Triage now; #1 AI Voice Tutor afterwards as a separate project.
- **Status:** valid. #1 not started.

### ADR-02: Free LLM providers: Gemini primary, Groq fallback
- **Context:** no Claude key, $0 budget. [H]
- **Options:** Claude (paid), OpenRouter (free tier ~50 requests/day; $10 credit unlocks more), Gemini free + Groq free, Azure OpenAI (often unavailable on student subscriptions).
- **Decision:** Gemini (Google AI Studio) primary, Groq fallback via LangChain `.with_fallbacks()`. Models are env-configurable (`CLASSIFIER_MODEL`, `DRAFTER_MODEL`, `FALLBACK_MODEL`). [V]
- **Trade-offs:** strict free quotas; Google may use free-tier prompts (OK for synthetic data only).
- **Status:** valid for the prototype; a paid tier is needed for real student data.

### ADR-03: Gemini 3.5 Flash-Lite for both steps
- **Context:** Gemini 2.5 models return 404 for new keys; `gemini-3.5-flash` free tier allows 20 requests/day (44/58 drafts silently fell back in eval 1). [H]
- **Decision:** `gemini-3.5-flash-lite` for classify **and** draft; thinking `minimal`; no temperature for lite models. [V]
- **Trade-offs:** slightly less capable drafter; it met the citation bar (88/88 verified).
- **Status:** valid. Revisit if a paid tier is used.

### ADR-04: LangChain + LangGraph + LangSmith
- **Context:** I first suggested direct SDK calls for simplicity; **the user explicitly asked for LangChain** (familiar) **and LangSmith** for tracing. [H]
- **Decision:** LangGraph `StateGraph` for the pipeline, LangChain chat models with structured output, LangSmith tracing when the key is set. [V]
- **Constraint:** the safety-critical logic (prechecks, citation verification, escalation) stays plain Python, not LangChain. [V]
- **Status:** valid.

### ADR-05: The escalation decision is deterministic code
- **Context:** the brief asks for "a clear escalation rule"; reviewers value predictability and testability. [H]
- **Decision:** the LLM produces signals (sentiment, at_risk, requires_human_action, confidence, kb_sufficient); `escalation.decide` applies fixed rules and lists every reason. [V]
- **Evidence:** the threshold sweep shows LLM confidence clusters around 0.95, so the safety must come from rules, not the confidence number. [V]
- **Status:** valid. **Don't move this decision into a prompt.**

### ADR-06: BM25 retrieval, no vector DB
- **Context:** 51 short passages. [V]
- **Decision:** `rank-bm25` over title + text; the classifier outputs an English `search_query` so Hinglish works; one search per issue for multi-issue tickets. [V]
- **Trade-offs:** depends on query rewriting; a poor rewrite leads to escalation via `kb_sufficient` / citation failure.
- **Status:** valid at this KB size.

### ADR-07: Citations verified in code
- **Decision:** the drafter must copy one exact sentence per `[n]`; code checks the passage exists and the quote matches (substring or ≥ 0.9 fuzzy) and that every marker has a citation; any failure escalates. Provider-agnostic. [V]
- **Status:** valid.

### ADR-08: Regex pre-checks before any LLM
- **Decision:** self-harm and prompt-injection phrases skip the LLM entirely (senior human; safety reply with the Tele-MANAS helpline); legal/chargeback/social-media threats flag the ticket. [V]
- **Trade-off:** catches common phrasings only.
- **Status:** valid.

### ADR-09: Never hide failures
- **Decision:** LLM failure → escalate with a holding reply; a failed outbound send → `send_failed`, shown under "Needs human" with the error. Added after the SMTP block made a failed send look like "Auto-replied". [V/H]
- **Status:** **non-negotiable.**

### ADR-10: SQLite + SQLAlchemy, seed on empty
- **Decision:** one `tickets` table with JSON columns; seed 12 tickets when empty, because free hosts wipe disk. [V]
- **Trade-off:** single process; ephemeral on Render. The `db.py` docstring overstates how easy a Postgres switch is.
- **Status:** OK for the demo; revisit for production (ADR-17).

### ADR-11: One Docker image; FastAPI serves the React build
- **Decision:** multi-stage Dockerfile, one URL, same image for Render/Azure/HF. [V]
- **Status:** valid.

### ADR-12: Hosting: Render live, Azure secondary, HF abandoned
- **Context:** HF Docker Spaces showed as paid; Azure for Students approval pending. [H]
- **Decision:** Render free web service + UptimeRobot keep-alive; Azure via the GHCR image later (cheaper than ACR); the HF workflow stays inactive. [V/H]
- **Status:** valid; Azure pending.

### ADR-13: Real channels share one flow (`inbound.py`)
- **Context:** the user wanted real email/WhatsApp intake, auto-replies without human approval when safe, and Senior Support called in when needed. [H]
- **Decision:** `process_incoming(channel, item)`. Auto-reply → send on the same channel. Escalate → acknowledgement + senior alert email; the agent approves in the Inbox and the reply goes out on the same channel. [V]
- **Status:** valid.

### ADR-14: Email: IMAP polling + Gmail API sending
- **Context:** polling needs no public URL; Render blocks SMTP. [H]
- **Decision:** a dedicated Gmail account; App Password for IMAP; Gmail API (OAuth Desktop client, scope `gmail.send`) for sending when `GMAIL_*` are set, SMTP otherwise. [V]
- **Status:** valid. Fragile on a brand-new consumer Gmail account (Google revoked the App Password once).

### ADR-15: WhatsApp via Meta Cloud API; Twilio kept as an alternative
- **Context:** Twilio trial rejects API sends (21654) and templates are paid; webhook delivery was unreliable. Unofficial WhatsApp Web libraries were rejected (ToS, ban risk). [H]
- **Decision:** Meta Cloud API with a permanent **System User** token; Twilio code kept (TwiML in-response replies). [V]
- **Status:** valid. Test number reaches only verified recipients.

### ADR-16: n8n dropped
- **Context:** in the JD, but the deadline was tight. [H]
- **Decision:** not built; listed as a future idea.

### ADR-17 (proposed, not implemented): Authentication and persistent storage
- **Context:** the live agent API is open; storage is ephemeral. [V]
- **Proposal:** an env-configured bearer token checked by a FastAPI dependency (excluding `/api/health` and webhooks); Postgres or Azure `/home` storage.
- **Status:** open. See `CURRENT_STATUS.md`.

---

## Constraints the next session must not violate

1. **No secrets** in code, docs, commits or chat. Only env variable names. `.env` stays git-ignored and docker-ignored.
2. **Tests stay hermetic:** keep `backend/tests/conftest.py` (blanks credentials, blocks real `httpx.post`); never let tests hit Gemini/Groq/Gmail/Meta/Twilio.
3. **Escalation stays deterministic code** (ADR-05), and **failures stay visible** (ADR-09).
4. **Prompt changes require bumping `PROMPT_VERSION`** in `config.py` (the cache key) and re-running the eval; KB changes invalidate the cache automatically via the fingerprint, but still need an eval re-run.
5. **Only one running instance may hold channel credentials** (otherwise duplicate replies).
6. **Don't recreate or delete** the Gmail OAuth client, App Password or Meta token casually: every copy (`.env`, Render) must be updated, and refresh tokens die with their client.
7. **Docs must stay honest:** report measured numbers only; mark unverified claims.
8. **Windows dev environment:** Python 3.12 venv at `.venv` (not the system 3.14), Git Bash or PowerShell.

## Working preferences the user expressed repeatedly [H]
- Step-by-step guidance for any console or dashboard work, one step at a time, with screenshots checked.
- Check for version and compatibility errors at **every** step; test each step.
- Never ask for keys in chat; the user pastes them into `.env` and host settings; verify them by fingerprint or behaviour, never by printing.
- Prefer free tiers; explain costs.
- Discuss the approach before large changes; the user makes the product decisions (e.g. option B for the courses KB, Meta over Twilio).

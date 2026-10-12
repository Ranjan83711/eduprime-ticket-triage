# CLAUDE.md: EduPrime Support Ticket Triage Agent

**Read [`PROJECT_HANDBOOK.md`](PROJECT_HANDBOOK.md) before making changes.** Current status and next steps: [`docs/CURRENT_STATUS.md`](docs/CURRENT_STATUS.md). After any significant change, update the handbook and the relevant `docs/*.md` file (status, decisions, history, troubleshooting).

## What this is
AI support-ticket triage agent (PW AI Engineer Intern assignment, problem #6) for a fictional edtech brand "EduPrime". It classifies student messages (email via Gmail, WhatsApp via Meta Cloud API, web form), drafts KB-grounded replies with code-verified citations, and a deterministic rule decides auto-reply vs escalate to a human team. Live on Render: https://eduprime-ticket-triage.onrender.com. **The project is functionally complete; don't rebuild or re-architect it.**

## Layout
- `backend/app/`: FastAPI app. `main.py` (routes, startup), `graph.py` (LangGraph pipeline), `llm.py` (Gemini + Groq fallback), `prechecks.py`, `kb.py` (BM25), `citations.py`, `escalation.py`, `prompts.py`, `schemas.py`, `triage.py` (cache), `db.py` (SQLite), `inbound.py` (shared channel flow), `email_channel.py`, `meta_whatsapp.py`, `whatsapp_channel.py` (Twilio), `config.py` (all env settings).
- `backend/data/kb/` (12 policy docs), `backend/data/tickets/` (64 test + 17 held-out), `backend/eval/` (runner + `report.json`), `backend/tests/` (75 tests), `backend/scripts/gmail_auth.py`.
- `frontend/src/`: React 19 + Vite 8 + Tailwind 4 + Recharts (Inbox, TicketDetail, EvalDashboard).
- `Dockerfile` (one image; FastAPI serves `frontend/dist`), `.github/workflows/docker-publish.yml` (CI).

## Commands (Windows, Git Bash, repo root)
```bash
.venv/Scripts/pip install -r backend/requirements.lock.txt            # Python 3.12 venv at .venv
cd frontend && npm ci && npm run build && cd ..
.venv/Scripts/python -m uvicorn app.main:app --app-dir backend --port 8000
cd backend && ../.venv/Scripts/python -m pytest -q                   # must stay 75+ passing, no network
cd backend && PYTHONIOENCODING=utf-8 ../.venv/Scripts/python -W ignore -m eval.run_eval   # ~15 min, uses LLM quota
```
For local runs, blank the channel variables (`EMAIL_ADDRESS= META_WA_TOKEN= TWILIO_ACCOUNT_SID= …`) so you don't answer real emails/WhatsApp in parallel with Render.

## Rules you must follow
1. **Never expose secrets.** Don't print, log, commit or ask the user to paste keys. Refer to env variable names only. Verify credentials by length, prefix, hash fingerprint or a read-only API call.
2. **Escalation stays deterministic Python** (`escalation.decide`). The LLM provides signals only.
3. **Never hide failures:** LLM errors → escalate with a holding reply; send errors → `send_failed`.
4. **Tests stay hermetic:** keep `backend/tests/conftest.py` (blanks creds, blocks `httpx.post`). Add tests with fakes for any new external call.
5. **Prompt change → bump `PROMPT_VERSION`** in `config.py`; prompt/KB/model change → re-run the eval and update the README numbers honestly.
6. **Only one running instance may hold channel credentials** (Render currently does).
7. **Don't delete or recreate** the Gmail OAuth client, App Password or Meta System User token; refresh tokens die with their client, and every copy (`.env`, Render) must match.
8. **Pushing to `main` redeploys Render** and resets the live inbox to the sample tickets; avoid needless pushes before demos.
9. **Match the surrounding code style:** small modules, plain functions, Pydantic schemas, short comments that explain *why*, httpx instead of SDKs for channels.
10. **Be honest in docs:** measured numbers only; mark unverified claims.

## Known pitfalls
- Free tiers: Gemini Flash-Lite 500 requests/day + per-minute limit (reset ~05:30 IST); `gemini-3.5-flash` only 20/day; Groq gpt-oss 8k tokens/min. Gemini 2.5 returns 404 for new keys; Gemini 3 rejects `thinking_budget=0` (use `thinking_level`).
- Render free blocks SMTP (hence the Gmail API), sleeps after 15 min (UptimeRobot keeps it awake), and wipes `/tmp` on deploy.
- Meta: the app must be subscribed to the WABA **and** the `messages` webhook field; dashboard temporary tokens last ~2 h; the app secret is 32 hex chars.
- Twilio trial can't send API messages (21654); TwiML in-response replies only.
- **No authentication on `/api/*`** (top open issue); the live inbox exposes senders' contacts.
- Git Bash: long heredocs with apostrophes can break; write a script file instead.

## User preferences
Step-by-step guidance for any dashboard/console work; check version compatibility at every step and test each step; free tools; discuss before big changes; the user decides product questions.

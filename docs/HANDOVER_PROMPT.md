# Handover Prompt

Paste everything inside the box below into a new Claude Code session opened in the project folder (the clone of `https://github.com/Ranjan83711/eduprime-ticket-triage`).

---

```text
You are taking over an existing, working project. Do not restart it, do not re-create existing
functionality, and do not refactor working code unless I ask. Continue from where development stopped.

PROJECT
"EduPrime Support Ticket Triage Agent": my submission for the PW (Physics Wallah) Central AI
"AI Engineer Intern" assignment, problem #6. It triages student support messages (email via Gmail,
WhatsApp via Meta Cloud API, web form), drafts replies grounded in a knowledge base with
citations verified in code, and a deterministic rule decides auto-reply vs escalate to a human team.
Stack: Python 3.12, FastAPI, LangGraph/LangChain, Gemini 3.5 Flash-Lite (Groq gpt-oss-120b fallback),
BM25, SQLite, React 19 + Vite + Tailwind, Docker on Render (live), LangSmith.
Live: https://eduprime-ticket-triage.onrender.com

STEP 1: READ, IN THIS ORDER
1. CLAUDE.md (rules you must follow)
2. PROJECT_HANDBOOK.md (complete overview)
3. docs/CURRENT_STATUS.md (what's done, what's open, priorities)
4. docs/DECISIONS.md (decisions and non-negotiable constraints)
5. docs/ARCHITECTURE.md, docs/DEVELOPMENT_HISTORY.md, docs/SETUP_AND_TROUBLESHOOTING.md as needed
6. README.md (public-facing summary with eval results)

STEP 2: RECONSTRUCT THE CURRENT STATE (read-only)
- git status, git log --oneline -15 (last known commit before handover docs: eb7f040)
- Check the code against the handbook; report any differences (don't fix them yet).
- Set up per docs/SETUP_AND_TROUBLESHOOTING.md if needed (Python 3.12 venv at .venv), then run
  the unit tests: cd backend && ../.venv/Scripts/python -m pytest -q   (expected: 75 passed, no network).
- Optionally GET https://eduprime-ticket-triage.onrender.com/api/health and summarise channel status.
- Do NOT run the full eval (it spends free LLM quota) and do NOT start a local server with the email or
  WhatsApp credentials loaded (it would answer real messages twice). Blank those variables for local runs.

STEP 3: REPORT BACK BEFORE CHANGING ANYTHING
Tell me: what the project does, what is complete, what is open (from docs/CURRENT_STATUS.md), the
test result, any drift between docs and code, and your recommended next step. Then wait for my go-ahead.

RULES (summary; details in CLAUDE.md and docs/DECISIONS.md)
- Never print, log, commit or ask me to paste secrets; I put keys in .env and Render myself.
  Refer to env variable names only; verify keys by fingerprint or a read-only call.
- Keep the escalation decision in plain Python (backend/app/escalation.py). Keep failures visible
  (escalate on LLM errors; mark send_failed on delivery errors).
- Keep tests hermetic (backend/tests/conftest.py). Add tests for anything new.
- A prompt change requires bumping PROMPT_VERSION; prompt/KB/model changes need an eval re-run, and the
  README numbers must be updated honestly.
- Don't delete/recreate the Gmail OAuth client, App Password or Meta System User token.
- Pushing to main redeploys Render and resets the live inbox; ask before pushing.
- Don't assume incomplete features are finished: authentication is NOT implemented, storage on Render is
  ephemeral, Azure deployment is pending, Twilio is blocked on its trial account.
- Guide me step by step for any dashboard or console work, and check for version/compatibility errors
  at every step.

CONTEXT YOU WON'T FIND IN CODE
- Free-tier limits observed: Gemini Flash-Lite 500 requests/day (+ per-minute), gemini-3.5-flash 20/day,
  Groq gpt-oss 8k tokens/min. Render free blocks SMTP (hence the Gmail API), sleeps after 15 min
  (UptimeRobot pings /api/health), wipes /tmp on deploy.
- Accounts: GitHub Ranjan83711 (public repo), Render service, UptimeRobot, support Gmail
  eduprime.support.demo@gmail.com (Google Cloud OAuth Desktop client, scope gmail.send), Meta app
  "EduPrime Triage" (System User token, never expires; test number only reaches verified recipients),
  Twilio trial (unused), Azure for Students (pending approval). The pitch deck lives in a private Claude
  Artifact on my old account (I have the PDF export); the demo video link is in the README.
- Next planned project: problem #1 "AI Voice Tutor" (separate repo, not started).
```

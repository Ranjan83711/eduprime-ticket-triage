# Current Status (as of 2026-10-12)

Repository: `main` at `eb7f040`, clean working tree, pushed. **75/75 tests pass** (`cd backend && ../.venv/Scripts/python -m pytest -q`).
Live: https://eduprime-ticket-triage.onrender.com (Render). Last verified live behaviour [H]: email auto-reply delivered via the Gmail API (2026-10-10), WhatsApp auto-reply delivered via the Meta permanent token (2026-10-10 06:11 UTC).
Labels: **[V]** verified · **[H]** from history · **[?]** unknown.

## 1. Status inventory

| Task / feature | Status | Done | Remaining | Files | Acceptance criteria |
|---|---|---|---|---|---|
| Triage pipeline (prechecks → classify → retrieve → draft → verify → decide) | **Complete** [V] | all nodes, error handling, fallback, retries, cache | — | `backend/app/graph.py`, `llm.py`, `escalation.py`, `citations.py` | tests pass; eval metrics as in the README |
| Evaluation harness and report | **Complete** [V] | 64 + 17 tickets, metrics, threshold sweep, dashboard | re-run after any prompt/KB/model change | `backend/eval/run_eval.py`, `eval/report.json` | report regenerated with 0 errors |
| React agent UI | **Complete** [V] | Inbox, detail, approve/send, delivery log, eval dashboard | — | `frontend/src/*` | `npm run build` succeeds; works against the API |
| Email channel (Gmail) | **Complete, live** [V/H] | IMAP poll, Gmail API send, ack + senior alert, agent replies, signature/quote stripping, loop prevention | depends on the App Password and OAuth token staying valid | `email_channel.py`, `inbound.py`, `scripts/gmail_auth.py` | email to the support address gets a threaded reply within ~1 min |
| WhatsApp via Meta Cloud API | **Complete, live** [V/H] | webhook verify + signature, background triage, Graph send, permanent System User token | only pre-verified recipient numbers (test number) | `meta_whatsapp.py`, `main.py` | message to the test number gets a reply |
| WhatsApp via Twilio | **Implemented, blocked on trial** [V/H] | signed webhook, TwiML replies, REST send | Twilio trial rejects REST sends (21654), templates paid-only; delivery to our webhook was unreliable during testing | `whatsapp_channel.py` | works with a paid Twilio account [?] |
| Docker image + CI | **Complete** [V] | multi-stage Dockerfile; Actions run tests and push to GHCR | — | `Dockerfile`, `.github/workflows/docker-publish.yml` | CI green on push |
| Render deployment | **Complete** [H] | live, auto-deploy, UptimeRobot keep-alive | storage is ephemeral (`/tmp`) | Render dashboard | `/api/health` ok; channels show no `last_error` |
| Azure deployment | **Blocked** [H] | image on GHCR; instructions written | Azure for Students approval; make the GHCR package public; create the Web App | README §Deployment | Web App serves the app with `DB_PATH=/home/data/triage.db` |
| Hugging Face deployment | **Abandoned** [H] | workflow exists | Docker Spaces need a paid plan | `.github/workflows/deploy-hf.yml` | — |
| README | **Complete** [V] | results, architecture SVG, models, cost, testing, limitations, config, video link | — | `README.md` | — |
| Pitch deck | **Complete** [H] | 5 slides with speaker notes (Claude Artifact) | the user exports a PDF and shares it publicly | external | PDF opens for anyone with the link |
| Demo video | **Complete** [H] | recorded; Google Drive link in README | sharing must be "Anyone with the link" [?] | `docs/demo-video-script.md` | link opens in Incognito |
| Assignment submission form | **Unknown** [?] | the user was filling it in | confirm it was submitted | — | confirmation received |
| Authentication for API / Inbox | **Not started** [V] | — | add auth (see §3) | `main.py`, `frontend/src/api.js` | unauthenticated requests to `/api/tickets*` get 401 |
| Persistent storage | **Not started** [V] | SQLAlchemy layer, `DB_PATH` folder creation | Azure `/home` or Postgres | `db.py`, `config.py` | tickets survive restarts |
| Problem #1 AI Voice Tutor | **Planned** [H] | — | separate project | new repo | — |

## 2. Known issues

1. **No authentication** on `/api/tickets`, `/api/tickets/{id}`, `/api/tickets/{id}/resolve` and `/api/triage` [V]. On the public deployment, real senders' emails and phone numbers are readable, and anyone can trigger replies through `/resolve`.
2. **Ephemeral storage on Render** [V/H]: every redeploy (including doc-only pushes) wipes tickets and reloads the 12 samples.
3. **Free-tier quotas** [H]: Gemini Flash-Lite 500 requests/day plus a per-minute limit; bursts fall back to Groq (wordier replies) or wait. p95 latency was 20 s during the eval while the email poller ran.
4. **Stale comments** [V]:
   - the `whatsapp_channel.py` module docstring describes background replies (the code uses TwiML within 12 s);
   - the `db.py` docstring claims a "one-line DB_URL change" (there's no URL setting).
5. **Eval report predates the channel work** [V]: generated 2026-10-09 10:25 UTC with prompt v5. The pipeline decision logic hasn't changed since. `result.channel` is now set to the arrival channel in `inbound.py`, which doesn't affect decisions [V]. The quote de-duplication runs on reply text only, not on decisions [V].
6. **Credential fragility** [H]: Google revoked the App Password once; recreating OAuth clients invalidates refresh tokens; Render values must match `.env` exactly.
7. **Single-process assumption** [V]: in-memory de-duplication sets and channel status, SQLite, one email poller. Never run two instances with channel settings.
8. **Labels are single-annotator and synthetic** [H]; T13 ("charged twice, please check") is arguably mislabelled.

## 3. Prioritised next actions

### Immediate
1. **Confirm the assignment submission**: GitHub repo, live link, deck PDF (shared "anyone with the link"), video (same).
2. **Keep the live demo healthy until the walkthrough:** check `/api/health` (both channels `last_error: null`); don't push unnecessary commits right before the call (each one resets the inbox); record after ~05:30 IST if Gemini quota matters.
3. **Prepare for the walkthrough** ("explain every design choice and change something on the spot"): practice small live changes, e.g. adding a pre-check regex, changing the confidence threshold via `AUTO_REPLY_CONFIDENCE`, adding a KB section (remember the eval and cache implications).

### High priority (if development continues)
1. **Add authentication** for the agent API and Inbox (e.g. a shared bearer token or basic auth via an env var, checked in a FastAPI dependency on every `/api/*` route except `/api/health` and the webhooks; the React app sends it). Acceptance: unauthenticated `GET /api/tickets` → 401; webhooks still work.
2. **Persistent storage:** Azure Web App with `/home/data`, or a `DATABASE_URL` setting plus Postgres (fix the misleading `db.py` docstring).
3. **Re-run the eval** after any prompt, KB or model change (`python -m eval.run_eval`, about 15 min on the free tier) and update the README numbers.

### Technical debt / reliability
- Fix the two stale docstrings (behaviour unchanged).
- Move de-duplication and status from memory to the DB if scaling beyond one instance.
- Indexes on `status`/`created_at` if ticket volume grows.
- Calibrated confidence (self-consistency) to make the threshold meaningful.

### Future enhancements (from README "What I'd do next")
- Registered WhatsApp business number (code already uses a permanent token).
- Order/refund status lookup from a payments system so status questions can be auto-answered.
- Agent edits fed back as new eval cases.
- Larger, independently labelled test set.
- n8n integration (originally planned, dropped for time).

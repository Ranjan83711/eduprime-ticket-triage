# Setup and Troubleshooting

Target: Windows 11, VS Code / Claude Code, Git Bash or PowerShell. The commands below were the ones actually used in the project [V/H].

---

## 1. Prerequisites

| Tool | Version used | Notes |
|---|---|---|
| Python | **3.12.10** (in `.venv`) | the system also had 3.14; the project deliberately uses 3.12. Installed with the Python install manager: `py install 3.12` |
| Node.js + npm | 24.21 / 12.1 | for the React build |
| Git + GitHub CLI | 2.55 / gh 2.101 | `gh auth status` must show `Ranjan83711` active for pushes |
| Docker Desktop | 29.8 (WSL 2) | optional; Render builds the Dockerfile itself |

## 2. First-time setup (Git Bash, from the repo root)

```bash
py -V:3.12 -m venv .venv
.venv/Scripts/python -m pip install --upgrade pip
.venv/Scripts/pip install -r backend/requirements.lock.txt     # exact versions (what Docker uses)
cp .env.example .env                                           # fill in values yourself (section 4)
cd frontend && npm ci && npm run build && cd ..
```
PowerShell equivalents: `.venv\Scripts\python.exe`, `.venv\Scripts\pip.exe`, `Copy-Item .env.example .env`.
`backend/requirements.txt` holds the unpinned direct dependencies; regenerate the lock with `pip freeze > backend/requirements.lock.txt` after deliberate upgrades.

## 3. Run, test, evaluate

```bash
# App (API + built UI) on http://localhost:8000
.venv/Scripts/python -m uvicorn app.main:app --app-dir backend --port 8000

# Frontend hot-reload (proxies /api to :8000)
cd frontend && npm run dev          # http://localhost:5173

# Unit tests: 75, no keys or network needed
cd backend && ../.venv/Scripts/python -m pytest -q

# Full evaluation: ~15 min on free tier, uses ~160 LLM calls of the daily quota
cd backend && PYTHONIOENCODING=utf-8 ../.venv/Scripts/python -W ignore -m eval.run_eval      # --no-cache, --delay 6, --limit N

# One-time Gmail API sign-in (writes GMAIL_REFRESH_TOKEN into .env)
cd backend && ../.venv/Scripts/python -m scripts.gmail_auth

# Docker
docker build -t eduprime-triage .
docker run --env-file .env -p 7860:7860 eduprime-triage
```
There's no linter configured in the repo [V].

> ⚠️ **If your `.env` contains email or WhatsApp settings, a local run starts reading the real inbox,** and every email gets answered twice if Render is also running. For local work, run with the channel variables blanked (python-dotenv doesn't override variables already set):
> ```bash
> EMAIL_ADDRESS= EMAIL_APP_PASSWORD= META_WA_TOKEN= META_APP_SECRET= TWILIO_ACCOUNT_SID= TWILIO_AUTH_TOKEN= DB_PATH=/tmp/local.db \
>   .venv/Scripts/python -m uvicorn app.main:app --app-dir backend --port 8001
> ```

### Basic end-to-end check
1. `GET http://localhost:8000/api/health` → `status: ok`, `keys.GOOGLE_API_KEY: true`, `kb_passages: 51`.
2. Open the UI, click the sample **"Video buffering"** → **Triage ticket** → green "Safe to auto-reply", citations "verified in KB".
3. Click the sample **"Prompt injection"** → escalated to Senior Support with no LLM calls in the trace.
4. **Evaluation** tab loads `eval/report.json`.

## 4. Configuration (`.env`; never commit, never paste in chat)

| Variable | Where to get it | Required |
|---|---|---|
| `GOOGLE_API_KEY` | aistudio.google.com → Get API key | yes |
| `GROQ_API_KEY` | console.groq.com → API Keys | yes (fallback) |
| `LANGSMITH_API_KEY`, `LANGSMITH_TRACING=true`, `LANGSMITH_PROJECT=eduprime-ticket-triage` | smith.langchain.com | optional |
| `EMAIL_ADDRESS` | the dedicated support Gmail | email channel |
| `EMAIL_APP_PASSWORD` | myaccount.google.com/apppasswords (needs 2-Step Verification with a phone second step, not only passkeys) | email channel |
| `SENIOR_SUPPORT_EMAIL` | any inbox for escalation alerts | email channel |
| `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET` | Google Cloud → enable Gmail API → Google Auth Platform: External, test user = the support account → Clients → **Desktop app** | Render (SMTP blocked) |
| `GMAIL_REFRESH_TOKEN` | written by `python -m scripts.gmail_auth` (open the printed link in a browser signed in as the support account) | Render |
| `META_WA_TOKEN` | Meta Business settings → System users → user with the app (Full control) and the WhatsApp account assigned → Generate token: expiry **Never**, scopes `whatsapp_business_messaging` + `whatsapp_business_management` | WhatsApp (Meta) |
| `META_WA_PHONE_NUMBER_ID` | Meta app → WhatsApp → API Setup ("Phone number ID", not the phone number) | WhatsApp (Meta) |
| `META_APP_SECRET` | Meta app → App settings → Basic → App secret (**32 hex chars**) | WhatsApp (Meta) |
| `META_WA_VERIFY_TOKEN` | any random string; enter the same value in Meta's webhook config | WhatsApp (Meta) |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` | Twilio console | WhatsApp (Twilio, optional) |
| Optional overrides | `CLASSIFIER_MODEL`, `DRAFTER_MODEL`, `FALLBACK_MODEL`, `META_GRAPH_VERSION` (v25.0), `TWILIO_WHATSAPP_FROM`, `AUTO_REPLY_CONFIDENCE` (0.7), `TOP_K_PASSAGES` (4), `DB_PATH`, `CACHE_DIR`, `EMAIL_POLL_SECONDS` (30), `IMAP_HOST`, `SMTP_HOST`, `SMTP_PORT` | — |

**Verify a key without revealing it:** check length/prefix or a hash fingerprint in Python (`hashlib.sha256(v.encode()).hexdigest()[:8]`), or make a read-only API call (e.g. Meta `GET /{phone_number_id}`, `debug_token`; Twilio `GET /Accounts/{sid}.json`; IMAP login).

## 5. Deployment

### Render (live)
- Web Service from the GitHub repo, language **Docker**, branch `main`, region Singapore, instance **Free**, health check `/api/health`. Render sets `PORT`; the Dockerfile's `CMD` uses it.
- Environment: the same keys as `.env` (all of section 4 that apply). Saving restarts the service.
- Every push to `main` redeploys (~2–4 min) and **resets the inbox to the sample tickets** (`/tmp`).
- **UptimeRobot**: HTTP(s) monitor on `https://eduprime-ticket-triage.onrender.com/api/health` every 5 min (prevents sleep, which would also stop the email poller).
- After deploying, check `/api/health`: `channels.email.last_error` and `channels.whatsapp_meta.last_error` should be null; `sender` should be `gmail_api`.

### Meta webhook (once)
1. Callback `https://<host>/api/whatsapp/meta-webhook`, verify token = `META_WA_VERIFY_TOKEN` → Verify and save.
2. Subscribe the **`messages`** field. Check with `GET /{app-id}/subscriptions?access_token={app-id}|{app-secret}`; the fields list must contain `messages`.
3. Subscribe the app to the WhatsApp Business Account: `POST /{waba-id}/subscribed_apps` with the token; `GET` must list the app.
4. Add your number as a recipient in API Setup (test numbers only reach verified recipients).

### Azure (pending)
Linux Web App for Containers, image `ghcr.io/ranjan83711/eduprime-ticket-triage:latest` (the GHCR package must be made **public** in GitHub → Packages), App Settings: keys + `WEBSITES_PORT=7860`, `DB_PATH=/home/data/triage.db`, `WEBSITES_ENABLE_APP_SERVICE_STORAGE=true`. Remove the channel settings from Render first if Azure takes over the channels.

---

## Troubleshooting

| Issue | Symptoms / error | Root cause | Resolution | Status |
|---|---|---|---|---|
| Docker won't start | "Virtualization support not detected" | BIOS VT-x was on; the WSL/Virtual Machine Platform features were off | admin: `wsl --install --no-distribution`, reboot | verified fixed |
| Tools "not found" | `node`/`docker` not recognised after install | old PATH in the running session | reopen the terminal/app, or reload PATH | verified |
| Slow pip install | >10 min | dependency resolution | use `requirements.lock.txt` | verified |
| Gemini model 404 | "no longer available to new users" | Gemini 2.5 retired for new keys though still listed | `gemini-3.5-*` | verified fixed |
| Gemini 400 | INVALID_ARGUMENT with `thinking_budget=0` | Gemini 3 uses `thinking_level` | `thinking_config={"thinking_level":"minimal"}` | verified fixed |
| Temperature warning | "uses fixed sampling defaults" | Flash-Lite ignores temperature | don't pass it for lite models | verified fixed |
| Groq model missing | Llama 3.3 not listed | Groq catalogue changed | `openai/gpt-oss-120b` | verified fixed |
| Drafts mostly on Groq | `fallback_calls` high | `gemini-3.5-flash` free tier = 20/day | Flash-Lite for drafting | verified fixed |
| Burst failures | Gemini 429 then Groq 429 | per-minute Gemini limit + Groq 8k TPM | whole-chain retry (10 s, 25 s); eval pacing 6 s | verified fixed |
| Daily quota | 429 `limit: 500 … PerDay` | eval runs used the 500/day | wait for reset (~05:30 IST); Groq covers | known limit |
| Too many escalations | 10 unnecessary | vague `requires_human_action` definition | rubric with examples in `CLASSIFIER_SYSTEM` | verified (10 → 2) |
| Replies copy KB text | "the student should…", duplicated sentences | Flash-Lite pastes quotes | drafter prompt + `strip_pasted_quotes` (same marker + ≥ 50% overlap only) | verified on 207 drafts |
| Stale cached answers after KB edit | old replies | cache key lacked KB content | `_kb_fingerprint()` in the key | verified fixed |
| Test leaks | fake results in the real cache; a test calling Google | tests used real cache/credentials | temp cache in tests; `conftest.py` blanks creds and blocks `httpx.post` | verified fixed |
| Form parsing crash risk | FastAPI needs `python-multipart` for `request.form()` | dependency missing | added to requirements | verified fixed |
| Gmail App Password page | "not available for your account" | 2-Step Verification not on (or passkeys only) | enable 2SV with a phone step | verified |
| IMAP login fails | `[ALERT] Invalid credentials` / `AUTHENTICATIONFAILED` | App Password revoked or mistyped (also once pasted wrong into Render) | create a new App Password; paste exactly into `.env` **and** Render | verified fixed |
| Email "sent" but not delivered (Render) | delivery error `Errno 101 Network is unreachable` | Render blocks outbound SMTP | Gmail API sending (`GMAIL_*`) | verified fixed |
| Failed send looked successful | ticket "Auto-replied" with no email | status ignored delivery result | `send_failed` status → Needs human | verified fixed |
| Gmail token errors | `disabled_client`, `unauthorized_client` | OAuth client deleted/recreated; token belongs to the old client | rerun `scripts.gmail_auth`; update `GMAIL_REFRESH_TOKEN` (and client ID/secret) in Render | verified fixed |
| `gmail_auth` timed out | no browser approval received | tab opened in another Chrome profile | paste the printed link into a window signed in as the support account | verified |
| Twilio replies never ours | Twilio "Standard auto-reply" | sandbox webhook URL not saved (still the demo URL) | set "When a message comes in" = our webhook, POST | verified |
| Twilio REST send fails | `21654 ContentSid Required` | newer trial sandbox sender requires templates; templates paid-only (`20003`) | TwiML in-response replies; or Meta | worked around; Twilio unreliable |
| Twilio error 12300 | logged on inbound messages | empty or unsupported webhook response (old code) | return `text/xml` TwiML | partially verified |
| Meta webhook silent | `received: 0` | app not subscribed to the WABA; no `messages` field | `subscribed_apps` + field subscription | verified fixed |
| Meta 403 on webhook | signature rejected | `META_APP_SECRET` pasted twice (64 chars) | 32-char secret in `.env` and Render | verified fixed |
| Meta send `131005` | "Access denied" | Render had an outdated temporary token; temporary tokens expire in ~2 h | System User token, expiry Never | verified fixed |
| System user token: "No permissions available" | can't pick scopes | app not assigned to the system user | assign the app (Full control) and the WhatsApp account; reload | verified |
| HF Space | Docker SDK shows paid | Hugging Face plan change | use Render | abandoned |
| GitHub Mermaid | "Unable to render rich display … reading 'render'" | GitHub Mermaid renderer error | static SVG `docs/architecture.svg` | verified fixed |
| Git Bash heredoc breaks | `unexpected EOF while looking for matching '` | apostrophes in long heredocs through the harness | write a script file, then run it | workaround |
| Slow test run | 40–90 s instead of ~5 s | machine load (no single slow test; `--durations` max < 1 s) | none needed | observed |

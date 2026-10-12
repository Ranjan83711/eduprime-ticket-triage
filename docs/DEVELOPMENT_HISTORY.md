# Development History

Reconstructed from `git log` (25 commits) and the development conversation. Times are IST (UTC+5:30). Commit hashes refer to `main`.
Labels: **[V]** verified in git/code · **[H]** from conversation history · **[I]** inference.

---

## Phase 0: Brief and planning (2026-10-08 evening → 2026-10-09 morning) [H]

- The user shared the assignment Google Doc (PW Central AI POD, "AI Engineer Intern Selection") and the JD file `AI Engineer Intern JD (1).docx` (git-ignored, not in the repo).
- **Decision:** do **#6 Support Ticket Triage** first, then **#1 AI Voice Tutor**.
- Stack discussion, in order:
  1. Proposed: FastAPI, React, Gemini/Claude, BM25, SQLite, Azure.
  2. The user has **no Claude API key** and a **$0 budget** → free Gemini.
  3. The user **asked for LangChain** (familiar) for **LangSmith tracing** → LangChain + LangGraph + LangSmith adopted.
  4. Deploy on **Azure (student account)** to show Azure skills **and** on a **free cloud** for the live demo.
  5. OpenRouter considered and rejected: its free tier is ~50 requests/day; with $10 credit it would have been simplest. The user chose **B: free Gemini + Groq**.
  6. **n8n dropped** because of the deadline.
  7. SQLite kept, with seed data on startup for ephemeral hosting.
- The user asked to be told every requirement on their side up front, and **asked me to check for version errors at every step** (a recurring instruction).

## Phase 1: Environment (2026-10-09 morning) [H]

| Problem | Root cause | Fix |
|---|---|---|
| Python 3.14 is "too new" | user preference for library compatibility | `py install 3.12` (Python install manager), `py -V:3.12 -m venv .venv` |
| `pip install` took >10 min | dependency resolution | let it finish; froze exact versions to `backend/requirements.lock.txt` so Docker doesn't re-resolve |
| Node/Docker "not found" after install | session PATH older than the installs | reload PATH in commands; reopening the app fixes it |
| Docker Desktop "Virtualization support not detected" | BIOS VT-x was **on**; the Windows hypervisor/WSL features were **off** | user ran `wsl --install --no-distribution` (admin) and rebooted → engine running |
| `gh` signed in as the wrong GitHub account | two accounts on the machine | user ran `gh auth login`; repo created under `Ranjan83711`; repo-local git identity set to the GitHub noreply address |

`58c6ab2` (12:29): initial commit (gitignore, env template, requirements) [V].

## Phase 2: Core pipeline (2026-10-09 12:29–12:53) [V]

- `6119289` (12:49): 11 KB docs, 60 labelled tickets, prechecks, citations, escalation, LangGraph graph, FastAPI, eval script, 25 tests. Tests used a fake LLM; a **leak was found**: API tests wrote fake results into the real cache → test cache redirected to a temp folder.
- `8f117d9` (12:53): **version errors found while probing live APIs** [H]:
  - `gemini-2.5-flash`/`-flash-lite` are listed by `models.list()` but return **404 "no longer available to new users"** → switched to `gemini-3.5-flash-lite` / `gemini-3.5-flash`.
  - Groq no longer serves `llama-3.3-70b-versatile` → `openai/gpt-oss-120b`.
  - `thinking_budget=0` → **400 INVALID_ARGUMENT** on Gemini 3 → `thinking_config={"thinking_level":"minimal"}` (also saved ~265 reasoning tokens and ~1.5 s per call).
  - Flash-Lite warns that `temperature` is ignored → not passed for "lite" models.
  - Prices taken from Google's official pricing page (third-party sites disagreed).

## Phase 3: Quality tuning and evaluation (2026-10-09 12:53–14:38) [V/H]

| Run | Result | Problem | Change |
|---|---|---|---|
| Eval 1 (prompt v1) | 98% category, 2 unsafe, **10 unnecessary escalations**; **44/58 drafts on Groq** | classifier set `requires_human_action` for anything money-related; `gemini-3.5-flash` free tier = **20 requests/day** | rewrote the rubric with examples; drafter → Flash-Lite; added held-out set |
| Eval 2 (v2/v3) | 0 unsafe, recall 100%, but **10 errors** | Gemini per-minute 429 **and** Groq 8k TPM exhausted together; `max_retries=1` | whole-chain retry (10 s, 25 s), pacing 6 s, thank-you fix (empty `issues` → no-citation rule skipped) |
| Eval 3 (v4) | **96.7% decisions, 0 unsafe, 2 unnecessary, 0 errors, 0 fallbacks**; held-out 100% | replies copied KB text in the third person ("the student should…") | drafter prompt: second person, quotes only in citations |

- `8b4b918` (13:13): prompt tuning, Flash-Lite drafting, retries, held-out set, Docker + workflows, React UI.
- `280cd8d` (13:29): final eval, README, screenshots.
- Docker image built and run locally (health, UI, real triage, path-traversal check) [H].
- `5d77e7a` (14:38): **quote de-duplication.** First attempt (remove any standalone quote) was **destructive**: running it over 207 cached real drafts showed it deleted facts that only appeared as quotes ("Hello! . ."). Second attempt removed the first match, which was sometimes the paraphrase. **Final rule:** remove a quote only if the previous sentence has the same marker and ≥ 50% word overlap → changes 6/207 drafts, all true duplicates [V/H].

## Phase 4: UI and email channel (2026-10-09 14:38–17:36) [V/H]

- The user asked for real channels instead of pasting tickets ("whatever comes to that mail id … it will raise the ticket … auto reply … stops for senior support").
- `0d646e9` (14:55): Gmail IMAP polling, threaded replies, acknowledgement + senior alert, agent replies, a `meta` column with an ad-hoc migration.
- Gmail App Password setup: the page said **"not available for your account"** until 2-Step Verification was enabled; the first App Password came from the wrong state and was rejected; the second worked [H].
- `ec51302`, `ea87e88`: Inbox live refresh (5 s), "New" badges, two-row filter header (the user reported a cramped header).
- `d0b614d`: signature stripping. A real external email arrived with "Sent from my iPhone" [H].
- `b5161b8`: a real pre-sales email ("Any course left for GATE CSE 2027?") was correctly **escalated** because the KB had no course info. The user chose **option B: add a Courses & Admissions KB doc** → 12 docs, 51 passages, 4 + 2 pre-sales tickets, KB fingerprint added to the cache key (editing the KB used to leave stale cached answers). Final eval: **96.9% / 0 unsafe / 88/88 citations**; held-out 94.1%.
- `69851de`: create the DB folder (for Azure `/home/data`).
- **Deployment:**
  - Hugging Face Docker Spaces showed as paid → not used.
  - Azure for Students applied for (pending, under another Microsoft account).
  - **Render** free tier chosen; `52b2372` adds the live link; **UptimeRobot** added for keep-alive.
- **Gemini daily quota (500/day) was exhausted** by the evals; live traffic ran on Groq until the reset (~05:30 IST) [H].
- `cd75d25` (16:59): **Render blocks outbound SMTP**: the live reply failed with `OSError [Errno 101] Network is unreachable`, and the ticket still said "Auto-replied". Two fixes:
  1. a `send_failed` status, so failed sends go to a human;
  2. **Gmail API over HTTPS** (Google Cloud project, Desktop OAuth client, test user, `scripts/gmail_auth.py` loopback sign-in; the first browser attempt timed out because the tab opened in the wrong Chrome profile, so the link was pasted into Incognito instead).
- `007d32d`: README for the above.

## Phase 5: WhatsApp (2026-10-09 22:16 → 2026-10-10 02:14) [V/H]

1. **Twilio** (`382bb0d`): signed webhook, background triage, REST replies. Found that `request.form()` needs **`python-multipart`** (missing → would crash in production); added it. Test-wide guard (`conftest.py`) added after a test made a real call to Google.
2. Twilio sandbox issues:
   - first, the webhook URL wasn't saved (Twilio kept answering with its own "Standard auto-reply");
   - then **error 12300** plus fallback auto-replies;
   - REST sends failed with **`21654 ContentSid Required`**: the account's newer trial sandbox number (+1 737 …) differs from the classic +1 415 523 8886, and Content templates are **paid-only**.
3. `5a7525c` (22:49): reply **inside the webhook response (TwiML)** via `ReplySlot` within 12 s, from the number the student messaged. A signed self-test to the live webhook proved our side worked; Twilio still didn't deliver user messages reliably (one arrived during a Render redeploy). Time-boxed and **stopped**; Twilio code kept as an alternative.
4. **Meta WhatsApp Cloud API** (`f29688f`, 01:24): verify handshake, HMAC-SHA256, background triage, Graph replies. `ef95079`: Graph **v25.0** (seen in the dashboard's curl sample). Setup problems, each diagnosed via the Graph API:
   - `META_APP_SECRET` was **64 chars = the 32-char secret pasted twice** → fixed in `.env`; `1c0b791` counts rejected signatures in `/api/health`.
   - The app wasn't **subscribed to the WhatsApp Business Account** (only Meta's internal "WA DevX" app was) → `POST /{waba}/subscribed_apps`.
   - The app webhook had **no `messages` field** subscribed → `POST /{app}/subscriptions fields=messages`.
   - After that the first real WhatsApp message was answered end to end.
5. `2f42534`: README WhatsApp section.

## Phase 6: Deliverables (2026-10-10) [V/H]

- 5-slide pitch deck built as a Claude Artifact (cover, problem, solution, how it works, results with a small "Next" line). The user asked for no separate "what's next" slide. Later updated to mention WhatsApp.
- `85a39a2`, `16d92c0`: demo video script (initially git-ignored, then pushed at the user's request with the personal email removed).
- Overnight: the **email channel broke**. The App Password was revoked (Google security on a brand-new account), and the user deleted/recreated the OAuth client (the old refresh token then gave `disabled_client`, the new client `unauthorized_client`). Fix: new App Password, rerun `gmail_auth`, update Render (the first Render paste was wrong → `AUTHENTICATIONFAILED`, second correct) [H].
- **WhatsApp replies broke**: `131005 Access denied`. Render had an older token, and **dashboard "temporary" tokens expire in ~2 h** (not 24 h). Fix next morning: **System User token, expiry Never**, scopes `whatsapp_business_messaging` + `whatsapp_business_management`. Generation first said "No permissions available" until the app (Full control) and the WhatsApp account were assigned to the system user [H].
- `cb630f0` (12:10): README: demo video link (Google Drive), stack, try-it line, permanent token, Render deployment, configuration table, fresh screenshots taken from a local copy with all channels disabled (no personal data).
- `eb7f040` (12:16): GitHub showed **"Unable to render rich display … reading 'render'"** for the README Mermaid diagram → replaced with a static `docs/architecture.svg`.
- The user recorded the demo video and was filling in the submission form (fields: problem statement, prototype link, GitHub link, pitch deck) [H]. Whether it was submitted is unknown.

## Phase 7: Handover documentation (2026-10-12) [V]

This documentation set (`PROJECT_HANDBOOK.md`, `CLAUDE.md`, `docs/*.md`) was written for migration to a company Claude account. No application code changed.

---

## Lessons learned

1. **Probe providers live; don't trust model lists or docs.** Retired models still appear in listings, defaults change between generations (thinking parameters), and free-tier quotas differ wildly by model.
2. **Measure every change** with the labelled set; check fixes against real outputs (the quote de-duplication bug would have shipped otherwise).
3. **Never hide failures.** A failed send must not look like success (`send_failed`).
4. **External setups fail silently;** diagnose through their APIs (Meta subscriptions, token debug, Twilio message log).
5. **Secrets must match exactly** across `.env` and the host; most "broken" moments were copy/paste mismatches or regenerated credentials.
6. **Free hosting has hidden limits:** blocked SMTP, sleeping instances, ephemeral disks.
7. **Tests must be hermetic:** a global guard against real HTTP calls caught a real leak.
8. **On Windows Git Bash,** long heredocs with apostrophes sometimes break the harness; writing a script file and running it is more reliable.

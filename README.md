# EduPrime Support Ticket Triage Agent

An AI agent that reads incoming student support queries (email / WhatsApp / web form, in English, Hindi or Hinglish), **classifies** them, **drafts a reply grounded in a knowledge base with verified citations**, and **decides: auto-reply or escalate to a human**, always saying why.

Built for the PW Central AI POD assignment, problem statement 6.

- **Live demo:** https://eduprime-ticket-triage.onrender.com
- **Demo video (3 min):** https://drive.google.com/file/d/15Ie29V_iDQUyFUAaXEHGqtdend-mHn-i/view?usp=sharing
- **Try it for real:** email `eduprime.support.demo@gmail.com` and get a reply in your thread within about a minute. WhatsApp runs on Meta's test number, which only reaches pre-verified numbers, so it's shown in the video.
- **Stack:** Python 3.12 · FastAPI · LangGraph + LangChain · Gemini 3.5 Flash-Lite (Groq gpt-oss-120b fallback) · BM25 · SQLite · React + Tailwind + Recharts · Docker on Render · LangSmith · Gmail API · Meta WhatsApp Cloud API

| Inbox (escalated ticket) | Evaluation dashboard |
|---|---|
| ![Inbox](docs/inbox.jpg) | ![Evaluation](docs/eval-dashboard.jpg) |

---

## Results (64 labelled tickets + 17 held-out)

| Metric | Main set (64) | Held-out set (17) |
|---|---|---|
| **Decision accuracy** (auto-reply vs escalate) | **96.9%** | **94.1%** |
| **Unsafe auto-replies** (needed a human, got a bot reply) | **0** | **0** |
| Unnecessary escalations | 2 | 1² |
| Escalation recall / precision | 100% / 92.6% | 100% / 87.5% |
| Category accuracy (primary label) | 98.4% | 88.2%¹ |
| Category micro-F1 (all labels, multi-issue tickets) | 0.952 | 0.950 |
| Angry-student recall | 100% | 100% |
| Citations whose quote really appears in the cited KB passage | **88 / 88 (100%)** | 22 / 23² |
| Latency per ticket (p50 / p95) | 2.9 s / 20 s³ | |
| Cost per 1,000 tickets (paid-tier prices; $0 on free tier) | **~$1.10** | |

¹ The held-out category "misses" are multi-issue tickets where the model found the right categories but listed them in a different order (micro-F1 ignores order).
² H17 ("batch for Class 8 CBSE?"): one citation failed verification, so the ticket was escalated instead of sent. That's the verifier doing its job: the only cost is a human reading a ticket the bot could have answered.
³ p95 includes free-tier rate-limit waits: the email poller was running and sharing the same quota during the eval. Without contention, p95 was 4.4 s in the previous run.

The **held-out set** was written after prompt tuning and never used to tune anything, so it is the honest check that the main-set numbers are not overfit. The full report, including per-ticket results, the confusion matrix and the threshold sweep, is in [`backend/eval/report.json`](backend/eval/report.json) and in the app's **Evaluation** tab.

---

## How it works

![Architecture: pre-checks, classify, retrieve, draft, verify citations, rule-based decision; auto-reply or escalate](docs/architecture.svg)

The pipeline is a **LangGraph** state machine ([`backend/app/graph.py`](backend/app/graph.py)):

1. **Pre-checks (no LLM):** regex rules flag self-harm, prompt injection, legal threats, chargeback/fraud and social-media threats, and extract order IDs and UTR numbers. Critical flags skip the LLM entirely and route straight to a senior human with a safe holding reply. Self-harm replies include the Tele-MANAS helpline. *Cheap, instant and auditable: the cases where we never want to depend on a model's judgement.*
2. **Classify:** structured output with categories (multi-label), confidence, sentiment, at-risk flag, *does this need a staff member to act?*, language, the distinct issues, and an **English search query** (so Hinglish tickets still retrieve English KB passages).
3. **Retrieve:** BM25 over 51 KB passages (12 markdown docs split by section), searched per issue so multi-issue tickets get passages for every issue.
4. **Draft:** a reply that uses only the retrieved passages, with `[n]` markers. Each citation must include an **exact sentence copied from the cited passage**.
5. **Verify citations:** code checks the passage ID exists and the quote really appears in it (normalised, with a 0.9 fuzzy tolerance for punctuation), and that every marker has a citation.
6. **Decide:** the escalation rule below.

### The escalation rule (code, not the LLM)

[`backend/app/escalation.py`](backend/app/escalation.py). A ticket is auto-replied **only if none** of these hold, and every reason that applies is shown to the agent:

| # | Rule | Routed to |
|---|---|---|
| 1 | Any pre-check flag (safety, injection, legal, chargeback, social media) | Senior Support |
| 2 | Student is angry or at risk of churning | Senior Support |
| 3 | Needs a staff member to act (approve a refund, trace a payment, activate a batch, process a batch change, replace books, persistent bug, status lookup) | Billing / Academic Ops / Tech Support / Support by category |
| 4 | Academic concept question | Subject Mentors |
| 5 | Classifier confidence below threshold (0.7) | by category |
| 6 | KB doesn't cover every issue, a citation failed verification, or an issue was answered without a citation | by category |

The LLM supplies the *signals* (sentiment, needs-action, confidence); the *decision* is deterministic, testable, and easy to change.

**Confidence threshold:** the sweep in the Evaluation tab shows the classifier's self-reported confidence clusters around 0.95, so the threshold makes almost no difference below 0.9. LLM confidence scores are poorly calibrated. That's why safety comes from rules 1–4 and 6 rather than the threshold, which is kept as a last guard for vague tickets (the prompt asks for low confidence on messages with no actual issue, e.g. "hello").

### Real email inbox

Tickets don't have to be pasted in: the app watches a real Gmail support inbox ([`email_channel.py`](backend/app/email_channel.py), [`inbound.py`](backend/app/inbound.py)).

- **Every 30 s** it reads unread mail over IMAP. It strips quoted earlier messages and signatures ("Sent from my iPhone"), and **ignores machine mail** (bounces, no-reply senders, out-of-office auto-replies), so it can never get into a reply loop.
- **Auto-reply:** the answer is sent **in the student's thread**, without `[n]` markers, with a "Help articles" list and the ticket number.
- **Escalate:** the student instantly gets an acknowledgement naming the team (self-harm cases get the helpline), and **Senior Support gets an alert email** with the reasons and the suggested draft. An agent edits it in the Inbox and clicks **Approve & send to …**, which sends it in the same thread.
- Every outbound message is logged on the ticket with its delivery status. A failed send is recorded and visible, never silently dropped.
- The Inbox refreshes live every 5 s and marks new tickets.

Setup: a dedicated Gmail account with 2-Step Verification and an App Password, then `EMAIL_ADDRESS`, `EMAIL_APP_PASSWORD` and `SENIOR_SUPPORT_EMAIL` in `.env`. Polling needs no public URL. **Sending:** SMTP by default; set `GMAIL_CLIENT_ID` / `GMAIL_CLIENT_SECRET` (a Google Cloud Desktop OAuth client) and run `python -m scripts.gmail_auth` once to send through the **Gmail API over HTTPS** instead. That's needed on Render's free tier, which blocks outbound SMTP: the first live test failed with `Network is unreachable`, the app recorded it as **send failed** and put the ticket in front of a human instead of showing "auto-replied". The OAuth scope is `gmail.send` only. **Run only one instance with these set**, otherwise each email gets answered twice.

### WhatsApp (Meta WhatsApp Cloud API)

Students can also message a WhatsApp number ([`meta_whatsapp.py`](backend/app/meta_whatsapp.py)); the flow is the same as email.

- Meta calls `/api/whatsapp/meta-webhook`. The one-time verify-token handshake is checked, and **every POST's `X-Hub-Signature-256` is verified with the app secret**, so forged requests are rejected (403, counted in `/api/health`).
- The webhook answers Meta immediately and triages in the background; the reply is sent through the Graph API as normal text. That's allowed within 24 h of the student's message, so no templates are needed. Escalations get an acknowledgement and a senior alert, and agents' approved replies go out on WhatsApp too.
- Duplicate deliveries (Meta retries) are ignored by message id; status updates and non-text messages are skipped.
- Auth uses a **System User access token that never expires** (scopes `whatsapp_business_messaging` and `whatsapp_business_management` only). The dashboard's "temporary" token lasts about 2 hours, which broke replies mid-demo the first time (`131005 Access denied`).
- Setup gotchas found while wiring it up, each diagnosed through the Graph API:
  - the app must be **subscribed to the WhatsApp Business Account** (`POST /{waba-id}/subscribed_apps`) **and** to the `messages` webhook field. Saving the callback URL alone delivers nothing.
  - an app secret pasted twice silently fails every signature check, which is why rejected signatures are counted in `/api/health`.
- Demo limit: Meta's free test number only messages up to 5 pre-verified recipients. Production would use a registered business number.
- A Twilio implementation ([`whatsapp_channel.py`](backend/app/whatsapp_channel.py)) is kept as an alternative. On a Twilio *trial*, the newer WhatsApp sandbox rejects API-sent free-form messages (error 21654) and templates are paid-only, so the app replies inside the webhook response (TwiML) when triage finishes within Twilio's 15 s window.

---

## Models and why

| Role | Model | Why |
|---|---|---|
| Classify | `gemini-3.5-flash-lite` | Short, well-specified task with native JSON-schema output. Fast and cheap. |
| Draft | `gemini-3.5-flash-lite` | Produced 100% verifiable citations in testing. See "What I tried" for why not Flash. |
| Fallback | `openai/gpt-oss-120b` on Groq | Different provider, so a Gemini outage or rate limit doesn't take the service down. Tested by forcing Gemini to fail. |
| Retrieval | BM25 (`rank-bm25`) | 51 short passages: keyword search is enough, explainable, and needs no embedding model or vector DB. |

**Settings:** Gemini thinking is set to `minimal`; on these tasks thinking added about 265 reasoning tokens and about 1.5 s per call without changing the output. `gpt-oss` runs with `reasoning_effort=low`.

**What I tried and changed (from measurements):**
- `gemini-2.5-flash`/`-flash-lite` are still listed by the API but return 404 for new keys, so I moved to the 3.5 family.
- `gemini-3.5-flash` as drafter: its **free tier allows only 20 requests/day**. In the first eval run, 44 of 58 drafts silently fell back to Groq. Flash-Lite already met the citation bar, so I use it for both steps.
- Gemini 3 rejects `thinking_budget=0` (Gemini 2.5 style) and Flash-Lite ignores `temperature`, so I use `thinking_level` instead and don't pass temperature.
- Groq's free tier allows only **8k tokens/minute**. When Gemini hit its per-minute limit, the burst of fallback calls also hit Groq's. Fix: retry the whole chain with backoff on 429, and pace the eval runner.
- First prompt version: 10 unnecessary escalations, because the classifier said "needs staff action" for anything money-related. I rewrote the definition with concrete examples (duplicate charges and failed payments resolve automatically per policy, etc.), and **unnecessary escalations went from 10 to 2 with 0 unsafe auto-replies**.
- Drafts first copied KB sentences verbatim in the third person ("the student should…"). The prompt now requires second person and keeps exact copies only in the citation field. Flash-Lite still occasionally pastes the quote right after its own paraphrase, so a small code step removes a quote **only** when the sentence before it cites the same marker and says the same thing. A first, simpler version (remove any standalone quote) deleted facts that appeared only as quotes; checking it against all 207 cached drafts caught that before shipping. The final rule changes 6 of 207 drafts, all true duplicates.

**Data note:** on the free tier, Google may use prompts to improve its models. That's fine here because every ticket is synthetic. Real student data would need the paid tier or Azure OpenAI with data-processing terms.

---

## Cost per run

Measured on the 64-ticket eval: about 1,650 tokens and 2 LLM calls per ticket.

| | Per ticket | Per 1,000 tickets |
|---|---|---|
| Free tier (what this demo uses) | $0 | $0 |
| Paid tier, Gemini 3.5 Flash-Lite ($0.30 / $2.50 per 1M tokens) | ~$0.0011 | **~$1.10** |

Critical pre-check tickets cost $0 (no LLM call). Results are cached by (ticket, models, prompt version), so repeated tickets cost nothing.

---

## How it was tested

- **75 unit tests** ([`backend/tests`](backend/tests)) with no API keys needed, run in CI on every push. They cover KB parsing and retrieval, every pre-check rule, citation verification (valid, fabricated quote, unknown passage, missing marker, punctuation tolerance), every escalation rule, the full LangGraph run with a fake LLM (happy path, critical flag skips the LLM, LLM failure escalates instead of crashing), rate-limit retry, cost accounting, the API, the email channel (parsing, signature/quote stripping, loop prevention, auto-reply, acknowledgement + senior alert, failed sends) against fake mail servers, and both WhatsApp integrations (Meta handshake, forged-signature rejection, retries de-duplicated, status updates ignored, agent replies; Twilio signature and TwiML replies). A test-wide guard blocks any real HTTP call, so tests can never touch real services even with live keys in `.env`.
- **Labelled test set:** 64 tickets ([`backend/data/tickets/test_set.json`](backend/data/tickets/test_set.json)) covering all categories, 12 Hinglish, 8 multi-issue, 4 pre-sales (course / admissions), angry and legal-threat tickets, prompt injection, a safety case, and edge cases ("hello", "thank you"). Each has gold categories, decision and sentiment.
- **Held-out set:** 17 more tickets written after tuning ([`holdout_set.json`](backend/data/tickets/holdout_set.json)).
- **Eval runner** ([`backend/eval/run_eval.py`](backend/eval/run_eval.py)): category accuracy and F1, confusion matrix, escalation precision/recall, unsafe auto-replies, sentiment, citation validity, latency, cost and fallback rate. The threshold sweep reuses stored outputs, so it costs no extra LLM calls.
- **LangSmith tracing:** every graph run (each node, prompt, tokens and latency) is traced to LangSmith when `LANGSMITH_API_KEY` is set.
- **End-to-end checks:** the Docker image was run locally (health, UI, a real triage); the fallback was tested by pointing the primary at a non-existent model; and real emails and WhatsApp messages were sent to the live deployment, checking each ticket's delivery log.

---

## Known limitations

- **Synthetic data.** The KB (fictional "EduPrime" policies) and all tickets were written by me, and the gold labels have a single annotator. Some labels are debatable: T13 "charged twice, please check" is labelled auto-reply (policy says duplicates are auto-refunded) but the model escalates it, which is arguably fine.
- **Prompt tuned on the main set.** The held-out set is the check against that, but at 17 tickets it is small.
- **Self-reported confidence is poorly calibrated** (see the threshold sweep). A better signal would be agreement across several samples, at extra cost.
- **Category "primary" ordering** on multi-issue tickets is unstable; it doesn't affect routing.
- **BM25 depends on the classifier's English search query** for Hinglish. If the rewrite is poor, retrieval is poor; the citation check plus `kb_sufficient` then escalate the ticket.
- **Regex pre-checks** catch common phrasings only. A rephrased injection or threat falls through to the LLM, which is still told to treat the ticket as data, and the reply can never trigger actions (there are no tools).
- **Free-tier rate limits:** under a burst of live traffic, requests wait and retry, and if both providers stay exhausted the ticket is escalated with a holding reply, never dropped.
- **Storage:** SQLite on a free host is wiped on restart; the inbox is re-seeded with sample tickets at startup. SQLAlchemy makes Postgres a connection-string change.
- **Channels:** email (Gmail) and WhatsApp (Meta Cloud API test number) are integrated. Manually pasted tickets have no channel, so "Approve & send" only logs those replies. The WhatsApp test number only reaches pre-verified recipients.
- **Free-tier Gmail on a brand-new account** got its App Password revoked once by Google's security checks; a real deployment would use a Google Workspace account or a service with a domain.

## What I'd do next

- Move WhatsApp to a registered business number (the code already uses a permanent system-user token).
- Look up order and refund status from the payments system, so status questions can be auto-answered instead of escalated.
- A calibrated confidence (self-consistency) and a larger, independently labelled test set.
- An agent-feedback loop: log agent edits to drafts and use them as new eval cases.

---

## Run locally

Requirements: Python 3.12, Node 20+, free API keys from [Google AI Studio](https://aistudio.google.com), [Groq](https://console.groq.com) and (optionally) [LangSmith](https://smith.langchain.com).

```bash
cp .env.example .env            # fill in the keys
python -m venv .venv
.venv/Scripts/pip install -r backend/requirements.lock.txt   # macOS/Linux: .venv/bin/pip
cd frontend && npm ci && npm run build && cd ..
.venv/Scripts/python -m uvicorn app.main:app --app-dir backend --port 8000
```

Open http://localhost:8000. For frontend development, run `npm run dev` in `frontend/`; it proxies `/api` to port 8000.

```bash
cd backend
../.venv/Scripts/python -m pytest -q          # unit tests, no keys needed
../.venv/Scripts/python -m eval.run_eval      # full eval (~15 min on free tier)
```

### Docker

```bash
docker build -t eduprime-triage .
docker run --env-file .env -p 7860:7860 eduprime-triage
```

## Deployment

One Docker image runs everywhere. FastAPI serves both the API and the built React app on one port.

- **Render (live demo):** a free Docker web service built straight from this repo, with automatic deploys on every push to `main`. **UptimeRobot** calls `/api/health` every 5 minutes so the free instance never sleeps (Render free sleeps after 15 min idle, which would also pause the email poller). Render's free tier blocks outbound SMTP, which is why email is sent through the Gmail API.
- **CI:** [`.github/workflows/docker-publish.yml`](.github/workflows/docker-publish.yml) runs the unit tests and publishes the image to `ghcr.io/ranjan83711/eduprime-ticket-triage` on every push.
- **Azure App Service (container):** the same GHCR image runs as a Linux Web App for Containers (settings as App Settings, `WEBSITES_PORT=7860`, `DB_PATH=/home/data/triage.db` for persistent storage). Pending Azure for Students approval at the time of writing.
- **Hugging Face Spaces:** [`.github/workflows/deploy-hf.yml`](.github/workflows/deploy-hf.yml) can mirror the repo to a Docker Space (needs `HF_TOKEN` and `HF_SPACE`); not used, since Docker Spaces now need a paid plan.

### Configuration

All settings are environment variables (`.env` locally, the host's settings in production); see [`.env.example`](.env.example).

| Variable | Needed for |
|---|---|
| `GOOGLE_API_KEY`, `GROQ_API_KEY` | LLM calls (Gemini primary, Groq fallback) |
| `LANGSMITH_API_KEY`, `LANGSMITH_TRACING`, `LANGSMITH_PROJECT` | Tracing (optional) |
| `EMAIL_ADDRESS`, `EMAIL_APP_PASSWORD`, `SENIOR_SUPPORT_EMAIL` | Email channel: read the inbox, send senior alerts |
| `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN` | Send via the Gmail API instead of SMTP (run `python -m scripts.gmail_auth` once) |
| `META_WA_TOKEN`, `META_WA_PHONE_NUMBER_ID`, `META_APP_SECRET`, `META_WA_VERIFY_TOKEN` | WhatsApp via Meta Cloud API |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` | WhatsApp via Twilio (alternative) |
| `CLASSIFIER_MODEL`, `DRAFTER_MODEL`, `FALLBACK_MODEL`, `AUTO_REPLY_CONFIDENCE`, `DB_PATH` | Optional overrides |

Each channel switches on only when its settings are present, and **only one running instance should have the channel settings**, otherwise every message gets answered twice.

## Project structure

```
backend/
  app/            graph.py (LangGraph), llm.py (Gemini + Groq fallback), prechecks.py, kb.py (BM25),
                  citations.py, escalation.py, prompts.py, schemas.py, db.py, main.py (FastAPI)
                  inbound.py (shared channel flow), email_channel.py (Gmail), meta_whatsapp.py (Meta),
                  whatsapp_channel.py (Twilio)
  scripts/        gmail_auth.py (one-time Gmail API sign-in)
  data/kb/        12 knowledge-base docs (markdown)
  data/tickets/   test_set.json (64), holdout_set.json (17)
  eval/           run_eval.py, report.json
  tests/          75 unit tests
frontend/src/     Inbox, TicketDetail, EvalDashboard (React + Tailwind + Recharts)
docs/             screenshots, demo-video-script.md
Dockerfile        multi-stage: build React, then Python runtime
```

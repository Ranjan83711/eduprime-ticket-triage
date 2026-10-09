"""FastAPI app: triage API, ticket inbox, eval report, and the built React frontend."""
import asyncio
import json
import os
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db, email_channel, inbound, meta_whatsapp, whatsapp_channel
from .config import (
    AUTO_REPLY_CONFIDENCE, BACKEND_DIR, CLASSIFIER_MODEL, DRAFTER_MODEL, FALLBACK_MODEL, ROOT_DIR,
    SENIOR_SUPPORT_EMAIL,
)
from .kb import get_kb
from .schemas import TicketIn
from .triage import triage

EVAL_REPORT = BACKEND_DIR / "eval" / "report.json"
WEBHOOK_REPLY_BUDGET_S = 12  # Twilio gives up at 15 s
HOLDING_WHATSAPP = "Thanks for your message! We're looking into it and will reply here shortly."
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    get_kb()
    email_channel.start_poller(lambda item: inbound.process_incoming("email", item))
    whatsapp_channel.init_status()
    meta_whatsapp.init_status()
    yield


app = FastAPI(title="EduPrime Ticket Triage", version="1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])


class ResolveIn(BaseModel):
    reply: str = Field(min_length=1, max_length=4000)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "models": {"classifier": CLASSIFIER_MODEL, "drafter": DRAFTER_MODEL, "fallback": FALLBACK_MODEL},
        "keys": {k: bool(os.getenv(k)) for k in ("GOOGLE_API_KEY", "GROQ_API_KEY", "LANGSMITH_API_KEY")},
        "auto_reply_threshold": AUTO_REPLY_CONFIDENCE,
        "kb_passages": len(get_kb().passages),
        "channels": {"email": {**email_channel.status, "senior_alerts_to": SENIOR_SUPPORT_EMAIL or None},
                     "whatsapp": whatsapp_channel.status, "whatsapp_meta": meta_whatsapp.status},
    }


@app.post("/api/triage")
async def triage_ticket(ticket: TicketIn):
    # The graph is synchronous; run it off the event loop so the server stays responsive.
    result = await run_in_threadpool(triage, ticket.text, ticket.channel)
    saved = db.save_result(result)
    return db.get_ticket(saved.id)


@app.get("/api/tickets")
def tickets(limit: int = 100):
    return db.list_tickets(limit)


@app.get("/api/tickets/{ticket_id}")
def ticket(ticket_id: int):
    t = db.get_ticket(ticket_id)
    if t is None:
        raise HTTPException(404, "ticket not found")
    return t


@app.post("/api/tickets/{ticket_id}/resolve")
def resolve(ticket_id: int, body: ResolveIn):
    t = db.resolve_ticket(ticket_id, body.reply)
    if t is None:
        raise HTTPException(404, "ticket not found")
    # Tickets that came from a real channel get the agent's reply on that channel.
    inbound.send_agent_reply(t, body.reply)
    return db.get_ticket(ticket_id)


@app.post("/api/whatsapp/webhook", include_in_schema=False)
async def whatsapp_webhook(request: Request):
    """Twilio calls this for each incoming WhatsApp message."""
    if not whatsapp_channel.enabled():
        raise HTTPException(404, "WhatsApp channel not configured")
    params = {k: str(v) for k, v in (await request.form()).items()}
    # Twilio signs the public URL it was given. Behind Render's proxy the app sees http://, so rebuild
    # the URL the way the client saw it before checking the signature.
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc))
    url = f"{proto}://{host}{request.url.path}" + (f"?{request.url.query}" if request.url.query else "")
    if not whatsapp_channel.valid_signature(url, params, request.headers.get("x-twilio-signature", "")):
        raise HTTPException(403, "invalid Twilio signature")

    item = whatsapp_channel.parse_webhook(params)
    reply = None
    if item and not whatsapp_channel.is_duplicate(item["message_sid"] or ""):
        whatsapp_channel.status["received"] += 1
        # Twilio waits up to 15 s. If triage finishes in time, the reply goes back in this response
        # (TwiML), which works even on trial accounts that block API-initiated messages. If not, the
        # student gets a holding message now and the pipeline keeps running and sends via the API.
        slot = inbound.ReplySlot()
        job = asyncio.ensure_future(run_in_threadpool(inbound.process_incoming, "whatsapp", item, slot))
        try:
            await asyncio.wait_for(asyncio.shield(job), timeout=WEBHOOK_REPLY_BUDGET_S)
        except asyncio.TimeoutError:
            pass
        reply = slot.close() or HOLDING_WHATSAPP
    return Response(content=whatsapp_channel.twiml(reply), media_type="text/xml")


@app.get("/api/whatsapp/meta-webhook", include_in_schema=False)
def meta_webhook_verify(request: Request):
    """Meta's one-time handshake when the webhook URL is saved in the app dashboard."""
    q = request.query_params
    challenge = meta_whatsapp.verify_subscription(q.get("hub.mode"), q.get("hub.verify_token"), q.get("hub.challenge"))
    if challenge is None:
        raise HTTPException(403, "verification failed")
    return PlainTextResponse(challenge)


@app.post("/api/whatsapp/meta-webhook", include_in_schema=False)
async def meta_webhook(request: Request, background: BackgroundTasks):
    """Meta posts each incoming WhatsApp message here, signed with the app secret."""
    if not meta_whatsapp.enabled():
        raise HTTPException(404, "Meta WhatsApp not configured")
    raw = await request.body()
    if not meta_whatsapp.valid_signature(raw, request.headers.get("x-hub-signature-256", "")):
        # Counted so a misconfigured app secret shows up in /api/health instead of failing silently.
        meta_whatsapp.status["rejected_signature"] = meta_whatsapp.status.get("rejected_signature", 0) + 1
        meta_whatsapp.status["last_error"] = "invalid signature: check META_APP_SECRET"
        raise HTTPException(403, "invalid signature")
    try:
        payload = json.loads(raw)
    except ValueError:
        raise HTTPException(400, "invalid JSON")
    for item in meta_whatsapp.parse_webhook(payload):
        if not meta_whatsapp.is_duplicate(item["message_id"] or ""):
            meta_whatsapp.status["received"] += 1
            # Meta only needs a quick 200; the reply goes out through the Graph API afterwards.
            background.add_task(inbound.process_incoming, "whatsapp", item)
    return {"status": "ok"}


@app.get("/api/kb")
def kb():
    return [p.model_dump() for p in get_kb().passages]


@app.get("/api/eval")
def eval_report():
    if not EVAL_REPORT.exists():
        raise HTTPException(404, "eval report not generated yet; run python -m eval.run_eval")
    return json.loads(EVAL_REPORT.read_text(encoding="utf-8"))


# Serve the React build (single deployable). API routes above take precedence.
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        file = (FRONTEND_DIST / path).resolve()
        inside = file.is_relative_to(FRONTEND_DIST.resolve())
        return FileResponse(file if path and inside and file.is_file() else FRONTEND_DIST / "index.html")

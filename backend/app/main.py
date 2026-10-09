"""FastAPI app: triage API, ticket inbox, eval report, and the built React frontend."""
import json
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db, email_channel, inbound
from .config import (
    AUTO_REPLY_CONFIDENCE, BACKEND_DIR, CLASSIFIER_MODEL, DRAFTER_MODEL, FALLBACK_MODEL, ROOT_DIR,
    SENIOR_SUPPORT_EMAIL,
)
from .kb import get_kb
from .schemas import TicketIn
from .triage import triage

EVAL_REPORT = BACKEND_DIR / "eval" / "report.json"
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    get_kb()
    email_channel.start_poller(lambda item: inbound.process_incoming("email", item))
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
        "channels": {"email": {**email_channel.status, "senior_alerts_to": SENIOR_SUPPORT_EMAIL or None}},
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

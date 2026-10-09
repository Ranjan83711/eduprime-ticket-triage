"""SQLite storage for processed tickets (SQLAlchemy, so Postgres is a one-line DB_URL change)."""
import json
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, create_engine, inspect, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.orm.attributes import flag_modified

from .config import DATA_DIR, DB_PATH
from .schemas import TriageResult

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


class Base(DeclarativeBase):
    pass


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    channel: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)
    decision: Mapped[str] = mapped_column(String(20))
    team: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # pending_review (escalated, waiting for a human) | auto_sent | sent_by_agent
    status: Mapped[str] = mapped_column(String(20))
    final_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    result: Mapped[dict] = mapped_column(JSON)
    # Where the ticket came from and what was sent back:
    # {"contact": "a@b.com", "subject": "...", "message_id": "...", "deliveries": [{...}]}
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    def to_dict(self) -> dict:
        r = self.result
        cls = r.get("classification") or {}
        return {
            "id": self.id, "created_at": self.created_at.isoformat(), "channel": self.channel, "text": self.text,
            "decision": self.decision, "team": self.team, "status": self.status, "final_reply": self.final_reply,
            "categories": cls.get("categories", []), "sentiment": cls.get("sentiment"),
            "confidence": cls.get("confidence"), "latency_ms": self.latency_ms, "cost_usd": self.cost_usd,
            "meta": self.meta or {}, "result": r,
        }


def init_db() -> None:
    Base.metadata.create_all(engine)
    # Databases created before the meta column existed: add it (create_all doesn't alter tables).
    if "meta" not in {c["name"] for c in inspect(engine).get_columns("tickets")}:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE tickets ADD COLUMN meta JSON"))
    seed_if_empty()


def add_delivery(ticket_id: int, delivery: dict) -> None:
    """Log an outbound message (auto-reply, acknowledgement, agent reply, alert) on the ticket."""
    with Session(engine) as s:
        t = s.get(Ticket, ticket_id)
        if t is None:
            return
        meta = dict(t.meta or {})
        meta["deliveries"] = [*meta.get("deliveries", []),
                              {**delivery, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}]
        t.meta = meta
        flag_modified(t, "meta")
        s.commit()


def save_result(result: TriageResult, meta: dict | None = None) -> Ticket:
    auto = result.decision.decision == "auto_reply"
    t = Ticket(
        channel=result.channel, text=result.ticket_text, decision=result.decision.decision,
        team=result.decision.team, status="auto_sent" if auto else "pending_review",
        final_reply=result.draft.reply if (auto and result.draft) else None,
        latency_ms=result.total_latency_ms, cost_usd=result.total_cost_usd, result=result.model_dump(mode="json"),
        meta=meta,
    )
    with Session(engine, expire_on_commit=False) as s:
        s.add(t)
        s.commit()
    return t


def list_tickets(limit: int = 100) -> list[dict]:
    with Session(engine) as s:
        return [t.to_dict() for t in s.scalars(select(Ticket).order_by(Ticket.id.desc()).limit(limit))]


def get_ticket(ticket_id: int) -> dict | None:
    with Session(engine) as s:
        t = s.get(Ticket, ticket_id)
        return t.to_dict() if t else None


def resolve_ticket(ticket_id: int, reply: str) -> dict | None:
    """A human agent sends (possibly edited) reply for an escalated ticket."""
    with Session(engine) as s:
        t = s.get(Ticket, ticket_id)
        if t is None:
            return None
        t.status, t.final_reply = "sent_by_agent", reply
        s.commit()
        return t.to_dict()


def seed_if_empty() -> None:
    """Free hosting wipes the disk on restart, so load a few pre-computed tickets for the demo inbox."""
    seed = DATA_DIR / "seed_results.json"
    if not seed.exists():
        return
    with Session(engine) as s:
        if s.scalar(select(Ticket.id).limit(1)) is not None:
            return
    for item in json.loads(seed.read_text(encoding="utf-8")):
        save_result(TriageResult.model_validate(item))

"""
SQLite storage. One file (data/aangan.db), no server.

Tables
  enquiries  one row per call (or, later, per WhatsApp thread / web form)
  events     an append-only log of everything that happened to an enquiry
  alerts     every Telegram message we posted (so a claim can update all of them)
"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS enquiries (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    channel             TEXT NOT NULL,
    external_id         TEXT NOT NULL,
    received_at         TEXT NOT NULL,          -- ISO 8601, IST
    caller_number       TEXT,
    caller_name         TEXT,
    duration_sec        INTEGER,
    answer_delay_sec    INTEGER,
    after_hours         INTEGER NOT NULL DEFAULT 0,

    call_type           TEXT,
    c1 TEXT, c2 TEXT, c3 TEXT, c4 TEXT, c5 TEXT, -- pass / fail / unclear / not_assessed
    agent_decision      TEXT,
    decision            TEXT,                   -- final, after the rubric check
    reason_code         TEXT,
    reason              TEXT,
    slot_text           TEXT,
    flags               TEXT NOT NULL DEFAULT '[]',   -- JSON list
    needs_review        INTEGER NOT NULL DEFAULT 0,
    review_reasons      TEXT NOT NULL DEFAULT '[]',
    pricing_violation   INTEGER NOT NULL DEFAULT 0,
    guardrail_report    TEXT NOT NULL DEFAULT '{}',
    related_enquiry_id  INTEGER,                -- e.g. the dropped call this one continues

    handoff_note        TEXT,
    claimed_by          TEXT,
    claimed_at          TEXT,
    realert_count       INTEGER NOT NULL DEFAULT 0,

    cost_voice_inr      REAL, cost_telephony_inr REAL, cost_llm_inr REAL,
    cost_messaging_inr  REAL NOT NULL DEFAULT 0,
    cost_basis          TEXT,                   -- "estimate" (from assumptions.yaml) or "platform" (Vaani's own figure)

    transcript          TEXT NOT NULL DEFAULT '[]',   -- JSON list of {speaker, text}
    recording_url       TEXT,
    agent_output        TEXT,                   -- JSON as received
    raw_payload         TEXT,                   -- JSON as received, for debugging
    is_demo             INTEGER NOT NULL DEFAULT 0,

    UNIQUE (channel, external_id)
);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    enquiry_id  INTEGER REFERENCES enquiries(id),
    at          TEXT NOT NULL,
    kind        TEXT NOT NULL,   -- received / alert_sent / claimed / realert / escalated / digest_sent / error
    detail      TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    enquiry_id  INTEGER NOT NULL REFERENCES enquiries(id),
    chat        TEXT NOT NULL,   -- designers / urgent / frontdesk
    chat_id     TEXT,
    message_id  INTEGER,         -- NULL in dry-run mode
    kind        TEXT NOT NULL,   -- first / realert / stale_to_urgent
    sent_at     TEXT NOT NULL,
    text        TEXT NOT NULL    -- what we posted, so a claim can re-render it
);

CREATE INDEX IF NOT EXISTS idx_enquiries_caller ON enquiries(caller_number, received_at);
"""

# Columns added after the first version. init_db adds any that an older database is missing,
# so you never have to delete data/aangan.db after pulling a change.
LATER_COLUMNS = {
    "cost_basis": "TEXT",
}

DB_PATH = config.DB_PATH
_ready: set[str] = set()   # databases whose schema we've already checked in this process


def _ensure_schema(conn: sqlite3.Connection):
    conn.executescript(SCHEMA)
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(enquiries)")}
    for column, sql_type in LATER_COLUMNS.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE enquiries ADD COLUMN {column} {sql_type}")


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        if str(DB_PATH) not in _ready:      # first use in this process (matters on Vercel cold starts)
            _ensure_schema(conn)
            _ready.add(str(DB_PATH))
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    _ready.discard(str(DB_PATH))
    with connect():
        pass


def as_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for key in ("flags", "review_reasons", "guardrail_report", "transcript", "agent_output"):
        if d.get(key):
            d[key] = json.loads(d[key])
    return d


def count_enquiries() -> int:
    with connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM enquiries").fetchone()[0]


def find_by_external_id(channel: str, external_id: str):
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM enquiries WHERE channel = ? AND external_id = ?", (channel, external_id)
        ).fetchone()
    return as_dict(row) if row else None


def recent_from_number(number: str, since_iso: str, before_iso: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """SELECT * FROM enquiries
               WHERE caller_number = ? AND received_at >= ? AND received_at < ?
               ORDER BY received_at DESC""",
            (number, since_iso, before_iso),
        ).fetchall()
    return [as_dict(r) for r in rows]


def insert_enquiry(record: dict) -> int:
    for key in ("flags", "review_reasons", "guardrail_report", "transcript", "agent_output", "raw_payload"):
        if key in record and not isinstance(record[key], str):
            record[key] = json.dumps(record[key], ensure_ascii=False)
    columns = ", ".join(record)
    placeholders = ", ".join("?" for _ in record)
    with connect() as conn:
        cur = conn.execute(f"INSERT INTO enquiries ({columns}) VALUES ({placeholders})", list(record.values()))
        return cur.lastrowid


def update_enquiry(enquiry_id: int, **fields):
    sets = ", ".join(f"{k} = ?" for k in fields)
    with connect() as conn:
        conn.execute(f"UPDATE enquiries SET {sets} WHERE id = ?", [*fields.values(), enquiry_id])


def get_enquiry(enquiry_id: int):
    with connect() as conn:
        row = conn.execute("SELECT * FROM enquiries WHERE id = ?", (enquiry_id,)).fetchone()
    return as_dict(row) if row else None


def list_enquiries(limit: int = 100) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM enquiries ORDER BY received_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [as_dict(r) for r in rows]


def log_event(enquiry_id, kind: str, detail: str = "", at: str | None = None):
    with connect() as conn:
        conn.execute(
            "INSERT INTO events (enquiry_id, at, kind, detail) VALUES (?, ?, ?, ?)",
            (enquiry_id, at or datetime.now().astimezone().isoformat(timespec="seconds"), kind, detail),
        )


# ── Alerts & claims ──────────────────────────────────────────────────────────
def record_alert(enquiry_id, chat, chat_id, message_id, kind, sent_at, text):
    with connect() as conn:
        conn.execute(
            "INSERT INTO alerts (enquiry_id, chat, chat_id, message_id, kind, sent_at, text) VALUES (?,?,?,?,?,?,?)",
            (enquiry_id, chat, chat_id, message_id, kind, sent_at, text),
        )


def alerts_for(enquiry_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM alerts WHERE enquiry_id = ? ORDER BY sent_at", (enquiry_id,)).fetchall()
    return [dict(r) for r in rows]


def claim(enquiry_id: int, who: str, at_iso: str) -> bool:
    """First tap wins. The WHERE claimed_by IS NULL makes two simultaneous taps safe."""
    with connect() as conn:
        cur = conn.execute(
            "UPDATE enquiries SET claimed_by = ?, claimed_at = ? WHERE id = ? AND claimed_by IS NULL",
            (who, at_iso, enquiry_id),
        )
        return cur.rowcount == 1


def unclaimed(decisions: tuple[str, ...]) -> list[dict]:
    marks = ",".join("?" for _ in decisions)
    with connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM enquiries WHERE claimed_by IS NULL AND decision IN ({marks}) AND is_demo = 0",
            decisions,
        ).fetchall()
    return [as_dict(r) for r in rows]


def enquiries_between(start_iso: str, end_iso: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM enquiries WHERE received_at >= ? AND received_at < ? ORDER BY received_at",
            (start_iso, end_iso),
        ).fetchall()
    return [as_dict(r) for r in rows]


def last_event(kind: str):
    with connect() as conn:
        row = conn.execute("SELECT * FROM events WHERE kind = ? ORDER BY id DESC LIMIT 1", (kind,)).fetchone()
    return dict(row) if row else None


# ── Logging helpers ──────────────────────────────────────────────────────────
def add_messaging_cost(enquiry_id: int, amount_inr: float):
    with connect() as conn:
        conn.execute("UPDATE enquiries SET cost_messaging_inr = cost_messaging_inr + ? WHERE id = ?",
                     (amount_inr, enquiry_id))


def events_for(enquiry_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM events WHERE enquiry_id = ? ORDER BY at, id", (enquiry_id,)).fetchall()
    return [dict(r) for r in rows]


EXPORT_COLUMNS = [
    "id", "channel", "received_at", "caller_name", "caller_number", "duration_sec", "answer_delay_sec",
    "after_hours", "call_type", "c1", "c2", "c3", "c4", "c5", "agent_decision", "decision", "reason_code",
    "reason", "slot_text", "flags", "needs_review", "pricing_violation", "claimed_by", "claimed_at",
    "realert_count", "cost_voice_inr", "cost_telephony_inr", "cost_llm_inr", "cost_messaging_inr", "cost_basis",
    "is_demo",
]


def export_rows() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(f"SELECT {', '.join(EXPORT_COLUMNS)} FROM enquiries ORDER BY received_at").fetchall()
    return [dict(r) for r in rows]

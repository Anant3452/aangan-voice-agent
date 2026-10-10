"""
Demo data: T01–T20 from the September enquiries file, as mock end-of-call payloads.

Used three ways:
  - tests/replay.py prints the decision table
  - tests/seed_demo.py loads them into your local database
  - on Vercel (DEMO_SEED=true) the app loads them into its empty /tmp database on first request

Demo rows are marked is_demo=1: the dashboard can hide them, re-alerts ignore
them, and nothing is posted to Telegram. Claims are SIMULATED (invented
designer names and times) so the claim-time numbers have something to show.
"""
import json
import threading
from datetime import timedelta
from pathlib import Path

from . import db, pipeline
from .channels import vaani_adapter
from .channels.vaani_adapter import MOCK_FIELD_MAP

CASES_DIR = Path(__file__).resolve().parent.parent / "demo" / "cases"

# Simulated claims: case id → (who, minutes after the call). Missing = left unclaimed on purpose.
CLAIMS = {
    "T01": ("Meera (designer)", 6),
    "T02": ("Kabir (designer)", 14),
    "T05": ("Nikhil Deshpande", 3),       # VIP referral, Nikhil took it himself
    "T06": ("Ira (designer)", 22),
    "T08": ("Kabir (designer)", 11 * 60 + 40),  # 10:47pm call, claimed next morning when alerts resumed
    "T09": ("Nikhil Deshpande", 9),       # complaint acknowledged
    "T12": ("Ira (designer)", 4),
    "T15": ("Meera (designer)", 31),
    "T17": ("Rohan (designer)", 18),
    # T20 left unclaimed so "Needs attention" has something in it
}


def load_cases() -> list[dict]:
    """All cases, in the order the calls happened (so T17a's dropped call comes before T17)."""
    cases = [json.loads(p.read_text()) for p in CASES_DIR.glob("*.json")]
    return sorted(cases, key=lambda c: c["call"]["started_at"])


def _set(payload: dict, dotted: str, value):
    *parents, last = dotted.split(".")
    for key in parents:
        payload = payload.setdefault(key, {})
    payload[last] = value


def case_to_payload(case: dict) -> dict:
    """Builds the webhook body using MOCK_FIELD_MAP, so it stays in sync when the real Vaani fields are mapped."""
    values = {
        "call_id": f"demo-{case['id']}",
        "started_at": case["call"]["started_at"],
        "duration_sec": case["call"]["duration_sec"],
        "caller_number": case["call"]["caller_number"],
        "answer_delay_sec": case["call"]["answer_delay_sec"],
        "transcript": case["transcript"],
        "structured_output": case["agent_output"],
    }
    payload: dict = {}
    for name, path in MOCK_FIELD_MAP.items():
        if values.get(name) is not None:
            _set(payload, path, values[name])
    return payload


def reset() -> int:
    with db.connect() as conn:
        ids = [r[0] for r in conn.execute("SELECT id FROM enquiries WHERE is_demo = 1")]
        marks = ",".join("?" * len(ids))
        if ids:
            conn.execute(f"DELETE FROM events WHERE enquiry_id IN ({marks})", ids)
            conn.execute(f"DELETE FROM alerts WHERE enquiry_id IN ({marks})", ids)
            conn.execute(f"DELETE FROM enquiries WHERE id IN ({marks})", ids)
    return len(ids)


def seed() -> int:
    added = 0
    for case in load_cases():
        enquiry = vaani_adapter.to_enquiry(case_to_payload(case))
        result = pipeline.process(enquiry, is_demo=True)
        if result["duplicate"]:
            continue
        added += 1
        if case["id"] in CLAIMS:
            who, minutes = CLAIMS[case["id"]]
            at = (enquiry.received_at + timedelta(minutes=minutes)).isoformat(timespec="seconds")
            db.update_enquiry(result["enquiry_id"], claimed_by=who, claimed_at=at)
            db.log_event(result["enquiry_id"], "claimed", f"{who} · {minutes} min after the call (simulated)", at)
    return added


_lock = threading.Lock()
_seeded = False


def seed_if_empty():
    """Vercel: each fresh instance starts with an empty /tmp database, so load the demo once."""
    global _seeded
    if _seeded:
        return
    with _lock:
        if not _seeded:
            if db.count_enquiries() == 0:
                seed()
            _seeded = True

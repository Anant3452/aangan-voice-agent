"""
Vaani end-of-call webhook  →  Enquiry

╔══════════════════════════════════════════════════════════════════════════╗
║  ⚠️  MOCK SCHEMA — THESE ARE NOT VAANI'S REAL FIELD NAMES                 ║
║                                                                          ║
║  We could not find public documentation of Vaani's end-of-call webhook   ║
║  payload. Every field name below is OUR placeholder.                     ║
║                                                                          ║
║  To connect the real Vaani:                                              ║
║    1. Make one test call and capture the real payload                    ║
║       (POST it to /webhooks/vaani/capture — it is saved to data/).       ║
║    2. Edit MOCK_FIELD_MAP so each value points at the real field path.   ║
║    3. If Vaani formats the transcript or timestamps differently, adjust  ║
║       _parse_transcript / _parse_time. Nothing else needs to change.     ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from .base import AdapterError, Enquiry, Turn

IST = ZoneInfo("Asia/Kolkata")

# Our name  →  dotted path into the incoming JSON.  MOCK — replace the right-hand side.
MOCK_FIELD_MAP = {
    "call_id":           "call_id",
    "started_at":        "started_at",            # ISO 8601 string or unix seconds
    "duration_sec":      "duration_seconds",
    "caller_number":     "from_number",
    "answer_delay_sec":  "ring_duration_seconds",  # time before the agent picked up
    "transcript":        "transcript",             # list of {role, text} or a plain string
    "recording_url":     "recording_url",
    "cost_inr":          "cost.total_inr",
    "structured_output": "analysis.structured_output",  # Part B JSON (dict or JSON string)
}

# Which transcript "role" values mean the agent spoke. MOCK — extend once known.
AGENT_ROLES = {"agent", "assistant", "bot", "ai"}


def _get(payload: dict, dotted_path: str):
    """Fetch payload['a']['b'] for 'a.b'. Returns None if any step is missing."""
    value = payload
    for key in dotted_path.split("."):
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def _parse_time(value) -> datetime:
    if value is None:
        return datetime.now(IST)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, IST)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise AdapterError(f"Unreadable timestamp: {value!r}") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=IST)


def _parse_transcript(value) -> list[Turn]:
    """Accepts either a list of {role/speaker, text/content} or 'Agent: …\\nCaller: …' text."""
    if not value:
        return []
    if isinstance(value, str):
        turns = []
        for line in value.splitlines():
            match = re.match(r"\s*([A-Za-z ]+?)\s*:\s*(.+)", line)
            if match:
                who = "agent" if match.group(1).strip().lower() in AGENT_ROLES else "caller"
                turns.append(Turn(who, match.group(2).strip()))
        return turns
    turns = []
    for item in value:
        role = str(item.get("role") or item.get("speaker") or "").lower()
        text = item.get("text") or item.get("content") or item.get("message") or ""
        turns.append(Turn("agent" if role in AGENT_ROLES else "caller", text))
    return turns


def _parse_structured(value):
    if value is None or isinstance(value, dict):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None  # pipeline marks the call for human review


def to_enquiry(payload: dict) -> Enquiry:
    f = {name: _get(payload, path) for name, path in MOCK_FIELD_MAP.items()}
    if not f["call_id"]:
        raise AdapterError(f"Missing call id (expected at '{MOCK_FIELD_MAP['call_id']}')")

    return Enquiry(
        channel="phone",
        external_id=str(f["call_id"]),
        received_at=_parse_time(f["started_at"]),
        caller_number=f["caller_number"],
        duration_sec=int(f["duration_sec"]) if f["duration_sec"] is not None else None,
        answer_delay_sec=int(f["answer_delay_sec"]) if f["answer_delay_sec"] is not None else None,
        transcript=_parse_transcript(f["transcript"]),
        agent_output=_parse_structured(f["structured_output"]),
        recording_url=f["recording_url"],
        platform_cost_inr=f["cost_inr"],
        raw_payload=payload,
    )

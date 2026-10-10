"""
The pipeline every enquiry goes through, whatever channel it came from:

    Enquiry ─► de-duplicate ─► rubric check ─► pricing guardrail ─► repeat-caller check
            ─► store ─► handoff note ─► route to Telegram
"""
import json
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from . import costs, db, handoff
from .channels.base import Enquiry
from .config import ASSUMPTIONS
from .guardrails import scan_agent_speech
from .notify import telegram
from .rules import criteria_results, reconcile

BIZ = ASSUMPTIONS["business"]
RULES = ASSUMPTIONS["rules"]
IST = ZoneInfo(BIZ["timezone"])


def normalise_phone(number):
    """Last 10 digits, so '+91 98xxx', '098xxx' and '98xxx' match as the same caller."""
    if not number:
        return None
    digits = "".join(ch for ch in str(number) if ch.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits or None


def is_after_hours(when: datetime) -> bool:
    local = when.astimezone(IST)
    open_t = time.fromisoformat(BIZ["front_desk_open"])
    close_t = time.fromisoformat(BIZ["front_desk_close"])
    closed_today = local.strftime("%A") in (BIZ.get("front_desk_closed_days") or [])
    return closed_today or not (open_t <= local.time() < close_t)


def _repeat_caller_checks(enquiry: Enquiry, received_iso: str, flags: list[str]):
    """Links call-backs after a dropped call, and spots callers we never followed up."""
    if not enquiry.caller_number:
        return None  # withheld number — nothing to match on
    window_start = (enquiry.received_at - timedelta(days=RULES["repeat_caller_window_days"]))
    earlier = db.recent_from_number(
        enquiry.caller_number, window_start.astimezone(IST).isoformat(), received_iso
    )
    related_id = None
    for prev in earlier:
        minutes_ago = (enquiry.received_at - datetime.fromisoformat(prev["received_at"])).total_seconds() / 60
        if "dropped_call" in prev["flags"] and minutes_ago <= RULES["dropped_call_merge_minutes"]:
            related_id = prev["id"]          # T17: same caller ringing back after the line dropped
            continue
        if prev["decision"] in ("Book", "Ask") and not prev["claimed_by"]:
            related_id = related_id or prev["id"]
            if "repeat_caller_no_followup" not in flags:
                flags.append("repeat_caller_no_followup")   # T16: we dropped the ball last time
    return related_id


def process(enquiry: Enquiry, is_demo: bool = False) -> dict:
    existing = db.find_by_external_id(enquiry.channel, enquiry.external_id)
    if existing:
        return {"enquiry_id": existing["id"], "decision": existing["decision"], "duplicate": True}

    enquiry.caller_number = normalise_phone(enquiry.caller_number)
    output = enquiry.agent_output or {}
    review_reasons: list[str] = []

    if not output:
        decision = "Ask"
        review_reasons.append("No structured output from the agent — a person must read the transcript.")
    else:
        decision, review_reasons = reconcile(output)

    guardrail = scan_agent_speech(enquiry.transcript)
    if guardrail["pricing_violation"]:
        review_reasons.append("Agent may have stated a price — see guardrail report.")

    flags = list(output.get("flags") or [])
    after_hours = is_after_hours(enquiry.received_at)
    if after_hours and "after_hours" not in flags:
        flags.append("after_hours")

    received_iso = enquiry.received_at.astimezone(IST).isoformat(timespec="seconds")
    related_id = _repeat_caller_checks(enquiry, received_iso, flags)

    results = criteria_results(output) if output else {}
    caller = output.get("caller") or {}
    record = {
        "channel": enquiry.channel,
        "external_id": enquiry.external_id,
        "received_at": received_iso,
        "caller_number": enquiry.caller_number or normalise_phone(caller.get("phone")),
        "caller_name": caller.get("name"),
        "duration_sec": enquiry.duration_sec,
        "answer_delay_sec": enquiry.answer_delay_sec,
        "after_hours": int(after_hours),
        "call_type": output.get("call_type"),
        "c1": results.get("c1_real_project"),
        "c2": results.get("c2_service_area"),
        "c3": results.get("c3_timeline"),
        "c4": results.get("c4_budget"),
        "c5": results.get("c5_decision_maker"),
        "agent_decision": output.get("decision"),
        "decision": decision,
        "reason_code": output.get("reason_code") or ("criteria_unclear" if not output else None),
        "reason": output.get("reason") or "; ".join(review_reasons),
        "slot_text": (output.get("consultation") or {}).get("slot_text"),
        "flags": flags,
        "needs_review": int(bool(review_reasons)),
        "review_reasons": review_reasons,
        "pricing_violation": int(guardrail["pricing_violation"]),
        "guardrail_report": guardrail,
        "related_enquiry_id": related_id,
        "transcript": [t.__dict__ for t in enquiry.transcript],
        "recording_url": enquiry.recording_url,
        "agent_output": output,
        "raw_payload": enquiry.raw_payload,
        "is_demo": int(is_demo),
        **costs.call_costs(enquiry.duration_sec, enquiry.platform_cost_inr),
    }
    enquiry_id = db.insert_enquiry(record)
    db.log_event(enquiry_id, "received", f"{enquiry.channel} · {decision}", at=received_iso)

    # T17: the earlier dropped call is now resolved by this call-back, so stop chasing it
    if related_id:
        earlier = db.get_enquiry(related_id)
        if "dropped_call" in earlier["flags"] and "continued_in_later_call" not in earlier["flags"]:
            db.update_enquiry(related_id, flags=json.dumps(earlier["flags"] + ["continued_in_later_call"]),
                              reason=f"Line dropped; caller rang back (enquiry #{enquiry_id}).")

    # The designer handoff note (not needed for declines)
    if decision != "Decline":
        note = handoff.build_note(db.get_enquiry(enquiry_id))
        db.update_enquiry(enquiry_id, handoff_note=handoff.render_text(note))

    # Telegram routing. A failure here must never lose the call; the
    # scheduler retries any Book/Escalate that has no alert yet.
    if not is_demo:
        try:
            telegram.route_new(enquiry_id)
        except Exception as exc:
            db.log_event(enquiry_id, "error", f"telegram: {exc}")

    return {
        "enquiry_id": enquiry_id,
        "decision": decision,
        "needs_review": bool(review_reasons),
        "review_reasons": review_reasons,
        "flags": flags,
        "duplicate": False,
    }

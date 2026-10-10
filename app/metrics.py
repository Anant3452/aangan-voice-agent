"""
Every number on the dashboard, computed from the database + assumptions.yaml.

Two halves, matching Nikhil's two questions:
  generates()  what the system is producing (calls, bookings, speed, pipeline)
  costs()      what it costs to run, per unit, projected per month, and the ROI
"""
from datetime import datetime
from statistics import median
from zoneinfo import ZoneInfo

from . import costs as cost_model
from . import db
from .config import ASSUMPTIONS

IST = ZoneInfo(ASSUMPTIONS["business"]["timezone"])
VOL = ASSUMPTIONS["volume"]
VAL = ASSUMPTIONS["value"]
VAR = ASSUMPTIONS["costs"]["variable"]

COST_PARTS = [  # (label, column on the enquiries row)
    ("Voice agent minutes", "cost_voice_inr"),
    ("Telephony", "cost_telephony_inr"),
    ("LLM usage", "cost_llm_inr"),
    ("Messaging", "cost_messaging_inr"),
]


def _pct(part, whole):
    return round(100 * part / whole, 1) if whole else None


def _minutes_between(a: str, b: str) -> float:
    return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() / 60


def load(start_iso: str, end_iso: str, include_demo: bool) -> list[dict]:
    rows = db.enquiries_between(start_iso, end_iso)
    return [r for r in rows if include_demo or not r["is_demo"]]


# ── What it generates ────────────────────────────────────────────────────────
def generates(rows: list[dict]) -> dict:
    calls = [r for r in rows if r["channel"] == "phone"]
    leads = [r for r in rows if r["decision"] in ("Book", "Ask", "Decline") and r["reason_code"] != "not_a_lead"]
    booked = [r for r in rows if r["decision"] == "Book"]
    escalations = [r for r in rows if r["decision"] == "Escalate"]

    with_delay = [r for r in calls if r["answer_delay_sec"] is not None]
    claim_mins = [_minutes_between(r["received_at"], r["claimed_at"]) for r in booked if r["claimed_at"]]
    ack_mins = [_minutes_between(r["received_at"], r["claimed_at"]) for r in escalations if r["claimed_at"]]

    declines: dict[str, int] = {}
    for r in rows:
        if r["decision"] == "Decline":
            declines[r["reason_code"] or "unknown"] = declines.get(r["reason_code"] or "unknown", 0) + 1

    by_hour = [{"hour": h, "office": 0, "after": 0} for h in range(24)]
    for r in calls:
        slot = by_hour[datetime.fromisoformat(r["received_at"]).astimezone(IST).hour]
        slot["after" if r["after_hours"] else "office"] += 1

    low, high = VAL["avg_project_value_inr_low"], VAL["avg_project_value_inr_high"]
    return {
        "calls_answered": len(calls),
        "answered_within_5_min_pct": _pct(sum(r["answer_delay_sec"] <= 300 for r in with_delay), len(with_delay)),
        "after_hours_pct": _pct(sum(r["after_hours"] for r in calls), len(calls)),
        "after_hours_count": sum(r["after_hours"] for r in calls),
        "new_enquiries": len(leads),
        "qualified_pct": _pct(len(booked), len(leads)),
        "qualified_leads": len(booked),                                   # passed the rubric (decision Book)
        "consultations_booked": sum(1 for r in booked if r["slot_text"]),  # …and agreed a slot on the call
        "decisions": {d: sum(r["decision"] == d for r in rows) for d in ("Book", "Ask", "Decline", "Escalate")},
        "decline_reasons": dict(sorted(declines.items(), key=lambda kv: -kv[1])),
        "escalations": len(escalations),
        "escalation_ack_median_min": round(median(ack_mins), 1) if ack_mins else None,
        "claim_median_min": round(median(claim_mins), 1) if claim_mins else None,
        "claim_within_1h_pct": _pct(sum(m <= 60 for m in claim_mins), len(claim_mins)),
        "claimed_leads": sum(1 for r in booked if r["claimed_at"]),
        "unclaimed_booked": sum(1 for r in booked if not r["claimed_at"]),
        "needs_review": sum(r["needs_review"] for r in rows),
        "pricing_violations": sum(r["pricing_violation"] for r in rows),
        "pipeline_inr_low": len(booked) * low,
        "pipeline_inr_high": len(booked) * high,
        "calls_by_hour": by_hour,
    }


# ── What it costs ────────────────────────────────────────────────────────────
def avg_call_seconds(all_calls: list[dict]) -> tuple[float, str]:
    """Real average once enough calls are logged; until then, derived from the T01–T20 transcripts."""
    real = [r["duration_sec"] for r in all_calls if r["duration_sec"] and not r["is_demo"]]
    if len(real) >= VOL["min_logged_calls_to_use_actuals"]:
        return sum(real) / len(real), f"average of {len(real)} logged calls"
    sample = list(VOL["transcript_durations_sec"].values())
    return sum(sample) / len(sample), f"average of {len(sample)} answered calls in the Sep 2026 transcripts"


def costs(rows: list[dict], gen: dict, days_in_period: float, monthly_calls: int, all_calls: list[dict]) -> dict:
    fixed_month = cost_model.fixed_monthly_total()

    # Actuals for the selected period: stored variable costs + fixed costs pro-rated by days
    breakdown = [{"label": label, "inr": round(sum(r[col] or 0 for r in rows), 2)} for label, col in COST_PARTS]
    breakdown.append({"label": "Hosting & fixed", "inr": round(fixed_month * days_in_period / 30, 2)})
    total = sum(b["inr"] for b in breakdown)

    def per(n):
        return round(total / n, 2) if n else None

    # Projection for a full month at the configured volume
    avg_sec, avg_source = avg_call_seconds(all_calls)
    unit = cost_model.call_costs(round(avg_sec))
    per_call = unit["cost_voice_inr"] + unit["cost_telephony_inr"] + unit["cost_llm_inr"]
    month_variable = per_call * monthly_calls
    month_total = month_variable + fixed_month

    qualified_share = (gen["qualified_pct"] / 100 if gen["qualified_pct"] is not None and gen["new_enquiries"] >= 10
                       else VAL["qualified_share_fallback"])
    month_qualified = monthly_calls * qualified_share

    # ROI: enquiries that used to wait 48h+ now get answered in minutes
    mid_value = (VAL["avg_project_value_inr_low"] + VAL["avg_project_value_inr_high"]) / 2
    slow_rate = VAL["slow_answer_conversion_rate"]
    lift = slow_rate * (VAL["fast_answer_conversion_multiplier"] - 1)
    recovered_projects = monthly_calls * VAL["no_response_48h_share"] * qualified_share * lift
    recovered_revenue = recovered_projects * mid_value
    breakeven_projects_per_month = month_total / (mid_value * VAL["gross_margin"])

    return {
        "period": {
            "breakdown": breakdown,
            "total_inr": round(total, 2),
            "per_enquiry_inr": per(len(rows)),
            "per_qualified_inr": per(gen["qualified_leads"]),
            "per_booked_inr": per(gen["consultations_booked"]),
            "days": round(days_in_period, 1),
        },
        "projection": {
            "monthly_calls": monthly_calls,
            "avg_call_sec": round(avg_sec),
            "avg_call_source": avg_source,
            "per_call_inr": round(per_call, 2),
            "per_call_parts": {k: unit[k] for k in ("cost_voice_inr", "cost_telephony_inr", "cost_llm_inr")},
            "variable_inr": round(month_variable),
            "fixed_inr": round(fixed_month),
            "total_inr": round(month_total),
            "qualified_share": round(qualified_share, 3),
            "per_enquiry_inr": round(month_total / monthly_calls, 2) if monthly_calls else None,
            "per_qualified_inr": round(month_total / month_qualified, 2) if month_qualified else None,
        },
        "roi": {
            "lost_enquiries_per_month": round(monthly_calls * VAL["no_response_48h_share"]),
            "recovered_projects_per_month": round(recovered_projects, 2),
            "recovered_revenue_inr": round(recovered_revenue),
            "monthly_cost_inr": round(month_total),
            "revenue_to_cost_multiple": round(recovered_revenue / month_total) if month_total else None,
            "breakeven_projects_per_month": round(breakeven_projects_per_month, 4),
            "breakeven_one_project_every_months": round(1 / breakeven_projects_per_month, 1)
            if breakeven_projects_per_month else None,
            "mid_project_value_inr": mid_value,
        },
    }


def compute(start_iso: str | None, end_iso: str, include_demo: bool, monthly_calls: int | None = None) -> dict:
    """start_iso=None means all time; fixed costs are then spread over the real span of the data."""
    rows = load(start_iso or "0000", end_iso, include_demo)
    all_calls = db.enquiries_between("0000", "9999")
    gen = generates(rows)
    if start_iso:
        days = max(_minutes_between(start_iso, end_iso) / 1440, 1)
    else:
        days = max(_minutes_between(rows[0]["received_at"], rows[-1]["received_at"]) / 1440, 1) if rows else 1
    return {
        "generated_at": datetime.now(IST).isoformat(timespec="seconds"),
        "range": {"start": start_iso, "end": end_iso, "include_demo": include_demo},
        "generates": gen,
        "costs": costs(rows, gen, days, monthly_calls or VOL["monthly_calls"], all_calls),
        "assumptions": {
            "variable": VAR,
            "fixed_monthly": ASSUMPTIONS["costs"]["fixed_monthly"],
            "value": VAL,
            "monthly_calls_default": VOL["monthly_calls"],
        },
        "attention": attention(include_demo),
        "recent": recent(rows),
    }


def attention(include_demo: bool) -> list[dict]:
    items = []
    for r in db.list_enquiries(500):
        if r["is_demo"] and not include_demo:
            continue
        if "continued_in_later_call" in r["flags"]:
            continue
        tags = []
        if r["decision"] in ("Book", "Escalate") and not r["claimed_by"]:
            tags.append("Unclaimed" if r["decision"] == "Book" else "Not acknowledged")
        if r["decision"] == "Ask":
            tags.append("Follow up")
        if r["needs_review"]:
            tags.append("Review")
        if r["pricing_violation"]:
            tags.append("Pricing guardrail")
        if tags:
            items.append({"id": r["id"], "when": r["received_at"], "name": r["caller_name"], "decision": r["decision"],
                          "reason": r["reason"], "tags": tags})
    return items[:25]


def recent(rows: list[dict]) -> list[dict]:
    out = []
    for r in sorted(rows, key=lambda r: r["received_at"], reverse=True)[:50]:
        project = (r.get("agent_output") or {}).get("project") or {}
        out.append({
            "id": r["id"], "when": r["received_at"], "name": r["caller_name"],
            "location": project.get("locality") or project.get("location_text"),
            "decision": r["decision"], "reason_code": r["reason_code"], "reason": r["reason"],
            "criteria": [r["c1"], r["c2"], r["c3"], r["c4"], r["c5"]],
            "claimed_by": r["claimed_by"],
            "claim_min": round(_minutes_between(r["received_at"], r["claimed_at"])) if r["claimed_at"] else None,
            "duration_sec": r["duration_sec"], "after_hours": bool(r["after_hours"]),
            "is_demo": bool(r["is_demo"]),
        })
    return out

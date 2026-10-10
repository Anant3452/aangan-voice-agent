"""
What each call costs. Every rate comes from config/assumptions.yaml → costs.

Stored on the call row at the moment it arrives (variable costs only);
messaging cost is added each time an alert is posted. Fixed monthly costs
(hosting, phone number) are spread over the month on the dashboard.
"""
import math

from .config import ASSUMPTIONS

VAR = ASSUMPTIONS["costs"]["variable"]
FIXED = ASSUMPTIONS["costs"]["fixed_monthly"]


def call_costs(duration_sec: int | None, platform_cost_inr: float | None = None) -> dict:
    minutes = (duration_sec or 0) / 60
    billed_telephony_min = math.ceil(minutes) if VAR["telephony_round_up_to_minute"] else minutes

    voice = minutes * VAR["voice_agent_inr_per_min"]
    llm = minutes * VAR["llm_inr_per_min"] + VAR["llm_post_call_inr"]
    basis = "estimate"
    if platform_cost_inr is not None:     # the platform told us what it actually charged
        voice, llm, basis = float(platform_cost_inr), 0.0, "platform"

    return {
        "cost_voice_inr": round(voice, 2),
        "cost_telephony_inr": round(billed_telephony_min * VAR["telephony_inr_per_min"], 2),
        "cost_llm_inr": round(llm, 2),
        "cost_messaging_inr": 0.0,
        "cost_basis": basis,
    }


def fixed_monthly_total() -> float:
    return float(sum(FIXED.values()))

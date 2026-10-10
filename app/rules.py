"""
qualified.md as code — the backend's independent check of the agent's decision.

The Vaani agent decides on the call. This module re-derives the decision from
the five criteria the agent reported. If the two disagree, the call is marked
for human review instead of being silently forwarded.
"""
CRITERIA = ["c1_real_project", "c2_service_area", "c3_timeline", "c4_budget", "c5_decision_maker"]
DECISIONS = {"Book", "Ask", "Decline", "Escalate"}


def criteria_results(agent_output: dict) -> dict[str, str]:
    criteria = (agent_output or {}).get("criteria") or {}
    return {c: (criteria.get(c) or {}).get("result", "unclear") for c in CRITERIA}


def expected_decision(agent_output: dict) -> str:
    """What qualified.md says the decision should be, given the reported criteria."""
    call_type = agent_output.get("call_type")
    if call_type in ("existing_client_complaint", "existing_client_query"):
        return "Escalate"          # complaints skip qualification entirely
    if call_type == "not_an_enquiry":
        return "Decline"

    results = criteria_results(agent_output)
    if "fail" in results.values():
        return "Decline"           # one clear fail closes gracefully (contradictions.md #2)
    if any(results[c] == "unclear" for c in CRITERIA[:3]):
        return "Ask"               # 1–3 still unclear after the one question
    return "Book"                  # 4 and 5 unclear count as qualified


def reconcile(agent_output: dict) -> tuple[str, list[str]]:
    """
    Returns (final_decision, review_reasons).
    - Agent and rubric agree      → that decision, no review.
    - Either says Escalate        → Escalate (never risk missing a complaint).
    - Otherwise they disagree     → the rubric's decision, and flag for review.
    """
    review = []
    agent_decision = agent_output.get("decision")
    rubric_decision = expected_decision(agent_output)

    if agent_decision not in DECISIONS:
        review.append(f"Agent gave no valid decision ({agent_decision!r}); used rubric.")
        return rubric_decision, review

    if agent_decision == rubric_decision:
        final = agent_decision
    elif "Escalate" in (agent_decision, rubric_decision):
        final = "Escalate"
        review.append(f"Agent said {agent_decision}, rubric said {rubric_decision}; escalated to be safe.")
    else:
        final = rubric_decision
        review.append(f"Agent said {agent_decision}, but the criteria imply {rubric_decision}.")

    if final == "Book" and not (agent_output.get("consultation") or {}).get("slot_text") \
            and not (agent_output.get("consultation") or {}).get("caller_constraints"):
        review.append("Booked but no consultation slot or availability captured.")

    return final, review

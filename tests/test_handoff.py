"""The designer note shows what was asked and hides what wasn't."""
from app import handoff

T14 = {
    "call_type": "new_enquiry",
    "caller": {"name": "Rahul", "phone": "+919800000014", "relationship_to_property": "family_of_owner",
               "acting_for": "parents (owners)"},
    "source": {"type": "unknown"},
    "project": {"segment": "residential", "property_type": "apartment", "bhk": "3BHK",
                "location_text": "Hadapsar", "zone": "pune_city", "scope_summary": "Full home design",
                "site_status": "possession_pending", "timeline_text": "Not specified; new possession"},
    "budget": {"volunteered": False, "caller_words": None},
    "criteria": {
        "c1_real_project": {"result": "pass", "evidence": "Parents want 'a proper design'"},
        "c2_service_area": {"result": "pass", "evidence": "Hadapsar"},
        "c3_timeline": {"result": "pass", "evidence": "New possession, no deadline"},
        "c4_budget": {"result": "pass", "evidence": "Not mentioned"},
        "c5_decision_maker": {"result": "unclear", "evidence": "Son researching; parents decide and will attend"},
    },
    "decision": "Book",
    "consultation": {"slot_text": "Sat 18 Oct, 10:30 am", "mode": "site_visit", "attendees": "Parents + son"},
    "uncertainties": ["Decision sits with parents, not the caller", "Carpet area not given"],
    "designer_brief": "Son calling for parents' new-possession 3BHK in Hadapsar. Parents decide and will attend.",
}

T09 = {
    "call_type": "existing_client_complaint",
    "caller": {"name": "Sheetal Deshpande", "phone": "+919800000009"},
    "criteria": {c: {"result": "not_assessed"} for c in
                 ["c1_real_project", "c2_service_area", "c3_timeline", "c4_budget", "c5_decision_maker"]},
    "decision": "Escalate",
    "escalation": {"urgency": "urgent", "issue_summary": "Designer hasn't replied in 5 days; project 3 months in",
                   "project_location": "2BHK, Viman Nagar", "assigned_designer": "Aryan",
                   "already_tried": "3 messages, 2 calls", "callback_requested_from": "Nikhil or a senior person",
                   "promised_callback": "Senior callback within 15 minutes"},
}


def record(out, decision, flags=()):
    return {"id": 7, "decision": decision, "received_at": "2026-09-17T11:41:00+05:30",
            "caller_number": "9800000014", "flags": list(flags), "review_reasons": [], "agent_output": out}


def test_budget_hidden_unless_volunteered():
    note = handoff.build_note(record(T14, "Book"))
    assert note["budget"] is None
    assert "Budget" not in handoff.render_text(note)


def test_budget_shown_in_callers_words_when_volunteered():
    out = {**T14, "budget": {"volunteered": True, "caller_words": "around 20 lakh"}}
    assert "around 20 lakh" in handoff.render_text(handoff.build_note(record(out, "Book")))


def test_covered_and_open_questions():
    note = handoff.build_note(record(T14, "Book", ["acting_on_behalf"]))
    assert "location" in note["covered"] and "timeline" in note["covered"]
    assert "who decides" in note["uncertainties"]          # c5 unclear → designer should confirm
    assert "Carpet area not given" in note["uncertainties"]
    assert any("acting for the owners" in f for f in note["flags"])


def test_complaint_note_is_about_the_problem_not_qualification():
    text = handoff.render_text(handoff.build_note(record(T09, "Escalate")))
    assert "URGENT" in text and "Aryan" in text and "Timeline" not in text


def test_telegram_render_escapes_html():
    out = {**T14, "caller": {**T14["caller"], "name": "<script>"}}
    assert "<script>" not in handoff.render_telegram(handoff.build_note(record(out, "Book")))

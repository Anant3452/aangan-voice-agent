"""The webhook, the adapter, the rubric check and the pricing guardrail."""
import copy

from fastapi.testclient import TestClient

from app.main import app

BOOKED = {
    "schema_version": "1.0",
    "call_type": "new_enquiry",
    "caller": {"name": "Priya", "phone": "+91 98000 00001"},
    "criteria": {
        "c1_real_project": {"result": "pass"},
        "c2_service_area": {"result": "pass"},
        "c3_timeline": {"result": "pass"},
        "c4_budget": {"result": "pass"},
        "c5_decision_maker": {"result": "pass"},
    },
    "decision": "Book",
    "reason_code": "qualified",
    "reason": "Full 3BHK redesign in Kothrud.",
    "consultation": {"slot_text": "Sat 11 Oct, 10:30 am"},
    "flags": ["referral"],
}


def payload(call_id, output, transcript=None, number="+919800000001", started="2026-10-10T14:00:00+05:30"):
    """Builds a request in our MOCK Vaani shape (see app/channels/vaani_adapter.py)."""
    return {
        "call_id": call_id,
        "started_at": started,
        "duration_seconds": 250,
        "from_number": number,
        "ring_duration_seconds": 3,
        "transcript": transcript or [{"role": "agent", "text": "Hello, Aangan Studio."},
                                     {"role": "user", "text": "Hi, I'm Priya."}],
        "analysis": {"structured_output": output},
    }


def test_booked_call_is_stored():
    with TestClient(app) as c:
        r = c.post("/webhooks/vaani", json=payload("t-book", BOOKED)).json()
        assert r["decision"] == "Book" and not r["needs_review"]


def test_duplicate_delivery_is_ignored():
    with TestClient(app) as c:
        c.post("/webhooks/vaani", json=payload("t-dup", BOOKED))
        assert c.post("/webhooks/vaani", json=payload("t-dup", BOOKED)).json()["duplicate"] is True


def test_agent_decision_that_breaks_rubric_goes_to_review():
    wrong = copy.deepcopy(BOOKED)
    wrong["criteria"]["c2_service_area"] = {"result": "fail", "evidence": "Talegaon"}
    with TestClient(app) as c:
        r = c.post("/webhooks/vaani", json=payload("t-wrong", wrong, number="+919800000002")).json()
        assert r["decision"] == "Decline" and r["needs_review"]


def test_complaint_always_escalates():
    complaint = {**BOOKED, "call_type": "existing_client_complaint", "decision": "Escalate",
                 "criteria": {k: {"result": "not_assessed"} for k in BOOKED["criteria"]}}
    with TestClient(app) as c:
        r = c.post("/webhooks/vaani", json=payload("t-esc", complaint, number="+919800000003")).json()
        assert r["decision"] == "Escalate" and not r["needs_review"]


def test_pricing_leak_is_flagged():
    leak = [{"role": "agent", "text": "For a 2BHK it's usually around 1,800 per sq ft."}]
    with TestClient(app) as c:
        r = c.post("/webhooks/vaani", json=payload("t-leak", BOOKED, leak, number="+919800000004")).json()
        assert r["needs_review"] and any("price" in x for x in r["review_reasons"])


def test_approved_pricing_line_is_not_flagged():
    ok = [{"role": "agent", "text": "Pricing depends on the site, the materials you choose, and the scope — "
                                     "your designer will walk you through it in detail at the consultation."}]
    with TestClient(app) as c:
        r = c.post("/webhooks/vaani", json=payload("t-ok", BOOKED, ok, number="+919800000005")).json()
        assert not r["needs_review"]


def test_repeat_caller_never_followed_up_is_flagged():
    with TestClient(app) as c:
        c.post("/webhooks/vaani", json=payload("t-rep1", BOOKED, number="+919800000006",
                                               started="2026-10-06T15:00:00+05:30"))
        r = c.post("/webhooks/vaani", json=payload("t-rep2", BOOKED, number="09800000006",
                                                   started="2026-10-09T10:38:00+05:30")).json()
        assert "repeat_caller_no_followup" in r["flags"]


def test_missing_structured_output_becomes_ask_for_review():
    with TestClient(app) as c:
        r = c.post("/webhooks/vaani", json=payload("t-none", None, number="+919800000007")).json()
        assert r["decision"] == "Ask" and r["needs_review"]


def test_bad_payload_is_rejected():
    with TestClient(app) as c:
        assert c.post("/webhooks/vaani", json={"nothing": "here"}).status_code == 422


def test_after_hours_is_detected():
    with TestClient(app) as c:
        r = c.post("/webhooks/vaani", json=payload("t-night", BOOKED, number="+919800000008",
                                                   started="2026-10-09T22:47:00+05:30")).json()
        assert "after_hours" in r["flags"]


def test_transcript_link_needs_signature():
    from app import links
    with TestClient(app) as c:
        eid = c.post("/webhooks/vaani", json=payload("t-link", BOOKED, number="+919800000009")).json()["enquiry_id"]
        assert c.get(f"/enquiries/{eid}/transcript").status_code == 404
        assert c.get(links.transcript_url(eid).replace("http://localhost:8000", "")).status_code == 200


def test_cron_tick_needs_token():
    with TestClient(app) as c:
        assert c.get("/tasks/tick").status_code == 401

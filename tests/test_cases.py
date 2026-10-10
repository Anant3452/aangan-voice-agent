"""Every T01–T20 case reaches the decision qualified.md expects."""
from fastapi.testclient import TestClient

from app import db
from app.demo import case_to_payload, load_cases
from app.main import app


def test_all_phone_cases_match_qualified_md():
    cases = load_cases()
    with TestClient(app) as c:
        results = {case["id"]: c.post("/webhooks/vaani", json=case_to_payload(case)).json() for case in cases}
    for case in cases:
        r = results[case["id"]]
        assert r["decision"] == case["expected"]["decision"], case["id"]
        assert not r["needs_review"], (case["id"], r["review_reasons"])

    rows = {r["external_id"]: r for r in db.list_enquiries(500)}
    assert rows["demo-T17"]["related_enquiry_id"] == rows["demo-T17a"]["id"]      # dropped call linked
    assert "continued_in_later_call" in rows["demo-T17a"]["flags"]               # …and no longer chased
    assert "after_hours" in rows["demo-T08"]["flags"]                           # 10:47pm
    assert "after_hours" in rows["demo-T20"]["flags"]                           # 9:15am, before the desk opens
    assert not any(r["pricing_violation"] for r in rows.values() if r["external_id"].startswith("demo-"))
    alerts = {a["chat"] for a in db.alerts_for(rows["demo-T16"]["id"])}
    assert alerts == {"frontdesk", "urgent"}                                     # repeat caller reaches Nikhil

"""Dashboard numbers and login."""
from fastapi.testclient import TestClient

from app import metrics
from app.main import app


def test_metrics_endpoint_shape():
    with TestClient(app) as c:
        m = c.get("/api/metrics?period=all").json()
    for key in ("calls_answered", "answered_within_5_min_pct", "after_hours_pct", "qualified_pct",
                "consultations_booked", "decline_reasons", "escalations", "claim_median_min", "pipeline_inr_low"):
        assert key in m["generates"]
    for key in ("per_enquiry_inr", "per_qualified_inr", "per_booked_inr", "breakdown"):
        assert key in m["costs"]["period"]
    assert "breakeven_one_project_every_months" in m["costs"]["roi"]


def test_average_call_length_derived_from_transcripts():
    sec, source = metrics.avg_call_seconds([])
    assert round(sec) == 287 and "transcripts" in source     # 4 min 47 s


def test_projection_at_200_calls():
    with TestClient(app) as c:
        p = c.get("/api/metrics?volume=200").json()["costs"]["projection"]
    assert p["monthly_calls"] == 200 and p["per_call_inr"] == 37.98
    assert p["total_inr"] == round(37.98 * 200 + 1300)


def test_dashboard_login(monkeypatch):
    import app.main as main
    monkeypatch.setattr(main, "DASHBOARD_PASSWORD", "secret")
    with TestClient(app) as c:
        assert c.get("/api/metrics").status_code == 401
        assert c.get("/api/metrics", auth=("aangan", "secret")).status_code == 200
        assert c.get("/health").status_code == 200        # webhooks/health never need the dashboard login


def test_enquiry_detail_for_drawer():
    from app import demo
    with TestClient(app) as c:
        c.post("/webhooks/vaani", json=demo.case_to_payload(demo.load_cases()[0]))
        eid = c.get("/api/enquiries").json()[0]["id"]
        d = c.get(f"/api/enquiries/{eid}").json()
    assert {"enquiry", "criteria", "note", "events", "transcript_url"} <= d.keys()

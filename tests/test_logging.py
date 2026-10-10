"""Every call stores its decision, claim time, cost and event timeline."""
import sqlite3

from fastapi.testclient import TestClient

from app import costs, db
from app.main import app
from tests.test_routing import T14_BOOK, send


def test_cost_estimate_for_an_average_call():
    c = costs.call_costs(287)                    # 4 min 47 s, the transcript average
    assert c["cost_voice_inr"] == 28.70          # 4.78 min × ₹6
    assert c["cost_telephony_inr"] == 4.00       # rounded up to 5 min × ₹0.80
    assert c["cost_llm_inr"] == 5.28             # 4.78 min × ₹1 + ₹0.50 extraction
    assert c["cost_basis"] == "estimate"


def test_platform_reported_cost_wins():
    c = costs.call_costs(287, platform_cost_inr=31.5)
    assert c["cost_voice_inr"] == 31.5 and c["cost_llm_inr"] == 0 and c["cost_basis"] == "platform"


def test_full_timeline_is_logged():
    with TestClient(app) as c:
        lead = send(c, "l-time", T14_BOOK, "+919822200001", "2026-10-08T11:00:00+05:30")
        c.post(f"/api/enquiries/{lead}/claim", json={"by": "Ananya"})
        kinds = [e["kind"] for e in c.get(f"/api/enquiries/{lead}/events").json()]
    assert kinds == ["received", "alert_sent", "claimed"]
    row = db.get_enquiry(lead)
    assert row["decision"] == "Book" and row["claimed_by"] == "Ananya" and row["claimed_at"]
    assert row["cost_voice_inr"] > 0 and row["cost_basis"] == "estimate"


def test_csv_export():
    with TestClient(app) as c:
        send(c, "l-csv", T14_BOOK, "+919822200002", "2026-10-08T12:00:00+05:30")
        r = c.get("/api/export.csv")
    header = r.text.splitlines()[0]
    assert r.status_code == 200 and "decision" in header and "cost_voice_inr" in header and "claimed_at" in header


def test_old_database_gets_new_columns(tmp_path, monkeypatch):
    old = tmp_path / "old.db"
    sqlite3.connect(old).executescript(
        "CREATE TABLE enquiries (id INTEGER PRIMARY KEY, channel TEXT NOT NULL, external_id TEXT NOT NULL,"
        " received_at TEXT NOT NULL, caller_number TEXT);")
    monkeypatch.setattr(db, "DB_PATH", old)
    db.init_db()
    cols = {r[1] for r in sqlite3.connect(old).execute("PRAGMA table_info(enquiries)")}
    assert "cost_basis" in cols

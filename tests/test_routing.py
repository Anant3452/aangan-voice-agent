"""Routing, claiming, re-alert ladder, daily digest (all in dry-run mode)."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app import db, scheduler
from app.main import app
from app.notify import email_digest
from tests.test_handoff import T09, T14
from tests.test_webhook import payload

IST = ZoneInfo("Asia/Kolkata")
T14_BOOK = {**T14, "reason_code": "qualified", "reason": "3BHK Hadapsar, parents decide", "flags": []}
T09_ESC = {**T09, "reason_code": "existing_client_complaint", "reason": "Designer unresponsive", "flags": []}


def send(c, call_id, out, number, started):
    return c.post("/webhooks/vaani", json=payload(call_id, out, number=number, started=started)).json()["enquiry_id"]


def chats(enquiry_id):
    return [(a["chat"], a["kind"]) for a in db.alerts_for(enquiry_id)]


def test_book_goes_to_designers_and_complaint_to_urgent():
    with TestClient(app) as c:
        lead = send(c, "r-book", T14_BOOK, "+919811100001", "2026-10-08T11:00:00+05:30")
        esc = send(c, "r-esc", T09_ESC, "+919811100002", "2026-10-08T11:05:00+05:30")
    assert chats(lead) == [("designers", "first")]
    assert chats(esc) == [("urgent", "first")]


def test_first_tap_wins():
    with TestClient(app) as c:
        lead = send(c, "r-claim", T14_BOOK, "+919811100003", "2026-10-08T11:00:00+05:30")
        first = c.post(f"/api/enquiries/{lead}/claim", json={"by": "Ananya"}).json()
        second = c.post(f"/api/enquiries/{lead}/claim", json={"by": "Rohan"}).json()
    assert first["claimed"] and not second["claimed"]
    assert db.get_enquiry(lead)["claimed_by"] == "Ananya"
    assert "Ananya" in second["message"]


def test_realert_ladder_then_overflow_to_urgent():
    with TestClient(app) as c:
        lead = send(c, "r-ladder", T14_BOOK, "+919811100004", "2026-10-08T11:00:00+05:30")
    day = datetime(2026, 10, 12, 10, 0, tzinfo=IST)            # a daytime clock we control
    db.update_enquiry(lead, received_at=(day - timedelta(minutes=1)).isoformat())
    with db.connect() as conn:
        conn.execute("UPDATE alerts SET sent_at = ? WHERE enquiry_id = ?", ((day - timedelta(minutes=1)).isoformat(), lead))

    for minutes in (5, 21, 42, 63, 84, 105):
        scheduler.tick(day + timedelta(minutes=minutes))
    kinds = [k for _, k in chats(lead)]
    assert kinds.count("realert") == 3 and kinds.count("stale_to_urgent") == 1
    assert ("urgent", "stale_to_urgent") in chats(lead)


def test_no_realerts_at_night():
    with TestClient(app) as c:
        lead = send(c, "r-night", T14_BOOK, "+919811100005", "2026-10-08T23:00:00+05:30")
    night = datetime(2026, 10, 13, 2, 0, tzinfo=IST)
    with db.connect() as conn:
        conn.execute("UPDATE alerts SET sent_at = ? WHERE enquiry_id = ?", ((night - timedelta(hours=2)).isoformat(), lead))
    scheduler.tick(night)
    assert [k for _, k in chats(lead)].count("realert") == 0
    scheduler.tick(night.replace(hour=8, minute=1))           # morning: alerts resume
    assert [k for _, k in chats(lead)].count("realert") == 1


def test_digest_contains_handoff_and_attention_items():
    with TestClient(app) as c:
        send(c, "r-dig1", T14_BOOK, "+919811100006", "2026-10-07T12:00:00+05:30")
        send(c, "r-dig2", T09_ESC, "+919811100007", "2026-10-07T13:00:00+05:30")
    subject, text, html = email_digest.build(datetime(2026, 10, 7, 9, 0, tzinfo=IST))
    assert "2 calls" in subject and "1 booked" in subject
    assert "Covered on the call" in text            # full handoff note is in the email
    assert "[UNCLAIMED]" in text and "NOBODY YET" in text
    assert "<h3>Needs attention</h3>" in html

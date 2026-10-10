"""
Runs once a minute: inside the server (local / VM), or triggered by an external
cron hitting /tasks/tick (Vercel, where nothing runs between requests). Two jobs:

1. Re-alerts. A qualified lead nobody has claimed is re-posted to the designers
   every 20 min (configurable), during alert hours only. After 3 tries it goes
   to Nikhil's urgent chat. An unacknowledged complaint is re-posted to the
   urgent chat every 10 min.
   It also sends any first alert that failed earlier (e.g. Telegram was down).

2. The daily digest. Once a day after `digest_time`, email yesterday's digest.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from . import db
from .config import ASSUMPTIONS
from .notify import email_digest, telegram

R = ASSUMPTIONS["routing"]
IST = ZoneInfo(ASSUMPTIONS["business"]["timezone"])

LADDERS = {
    #             chat to re-post in, minutes between, max re-posts, then where
    "Book":     ("designers", R["lead_realert_minutes"], R["lead_max_realerts"], "urgent"),
    "Escalate": ("urgent", R["complaint_realert_minutes"], R["complaint_max_realerts"], None),
}


def _realert(e: dict, now: datetime):
    chat, every, max_tries, overflow = LADDERS[e["decision"]]
    alerts = db.alerts_for(e["id"])

    if not alerts:                                    # first alert never went out
        telegram.route_new(e["id"], now)
        return

    may_buzz = telegram.in_alert_hours(now) or (e["decision"] == "Escalate" and R["complaints_ignore_alert_hours"])
    last = max(datetime.fromisoformat(a["sent_at"]) for a in alerts)
    if not may_buzz or now - last < timedelta(minutes=every):
        return

    waited = (now - datetime.fromisoformat(e["received_at"])).total_seconds() / 60
    tries = sum(a["kind"] == "realert" for a in alerts)
    if tries < max_tries:
        telegram.post(e, chat, "realert", now, f"⏰ <b>Still unclaimed after {waited:.0f} min</b>")
        db.update_enquiry(e["id"], realert_count=tries + 1)
    elif overflow and not any(a["kind"] == "stale_to_urgent" for a in alerts):
        telegram.post(e, overflow, "stale_to_urgent", now,
                      f"🔴 <b>No designer has claimed this lead in {waited:.0f} min.</b> Please assign someone.")


def _maybe_send_digest(now: datetime):
    local = now.astimezone(IST)
    if local.time() < time.fromisoformat(R["digest_time"]):
        return
    last = db.last_event("digest_sent")
    if last and last["at"][:10] == local.date().isoformat():
        return
    result = email_digest.send(local - timedelta(days=1))
    db.log_event(None, "digest_sent", result, local.isoformat(timespec="seconds"))


def tick(now: datetime | None = None):
    now = now or datetime.now(IST)
    for e in db.unclaimed(("Book", "Escalate")):
        try:
            _realert(e, now)
        except Exception as exc:   # one bad alert must not stop the others
            db.log_event(e["id"], "error", f"re-alert: {exc}")
    try:
        _maybe_send_digest(now)
    except Exception as exc:
        db.log_event(None, "error", f"digest: {exc}")

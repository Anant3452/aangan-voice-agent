"""
Telegram routing.

  Book      → designers group, with a "✋ Claim this lead" button
              (+ a copy to the urgent chat if it's a priority repeat caller, VIP or large project)
  Escalate  → urgent chat only (Nikhil + seniors), with a "✅ I'm on it" button
  Ask       → front-desk chat, if configured (otherwise the daily digest covers it)
  Decline   → not posted; it's in the digest and the dashboard

The first person to tap the button claims it; every copy of the alert is then
edited to say who claimed it and how long after the call.

No TELEGRAM_BOT_TOKEN in .env  →  DRY RUN: nothing is sent, every message is
written to data/outbox.log instead, so the whole flow can be demoed offline.
"""
from datetime import datetime, time
from html import escape
from zoneinfo import ZoneInfo

import requests

from .. import db, handoff
from ..config import (ASSUMPTIONS, DB_PATH, TELEGRAM_BOT_TOKEN, TELEGRAM_DESIGNERS_CHAT_ID,
                      TELEGRAM_FRONTDESK_CHAT_ID, TELEGRAM_URGENT_CHAT_ID)

ROUTING = ASSUMPTIONS["routing"]
IST = ZoneInfo(ASSUMPTIONS["business"]["timezone"])
OUTBOX = DB_PATH.parent / "outbox.log"   # dry-run messages land next to the database

CHATS = {
    "designers": TELEGRAM_DESIGNERS_CHAT_ID,
    "urgent": TELEGRAM_URGENT_CHAT_ID,
    "frontdesk": TELEGRAM_FRONTDESK_CHAT_ID,
}
PRIORITY_FLAGS = {"repeat_caller_no_followup", "vip_referral", "large_project"}


# ── Low-level API call ───────────────────────────────────────────────────────
def api(method: str, **params) -> dict:
    """Calls the Telegram Bot API, or writes to data/outbox.log in dry-run mode."""
    if not TELEGRAM_BOT_TOKEN:
        OUTBOX.parent.mkdir(parents=True, exist_ok=True)
        with OUTBOX.open("a", encoding="utf-8") as fh:
            fh.write(f"\n── DRY RUN {method} @ {datetime.now(IST):%d %b %H:%M:%S} → chat {params.get('chat_id')}\n")
            fh.write(f"{params.get('text', '')}\n")
            if params.get("reply_markup", {}).get("inline_keyboard"):
                fh.write(f"[buttons: {params['reply_markup']['inline_keyboard']}]\n")
        return {"message_id": None}
    resp = requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}", json=params, timeout=10)
    body = resp.json()
    if not body.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {body.get('description')}")
    return body["result"]


def in_alert_hours(now: datetime) -> bool:
    start = time.fromisoformat(ROUTING["alert_hours_start"])
    end = time.fromisoformat(ROUTING["alert_hours_end"])
    return start <= now.astimezone(IST).time() < end


# ── Posting ──────────────────────────────────────────────────────────────────
def _button(enquiry: dict) -> dict:
    label = "✅ I'm on it" if enquiry["decision"] == "Escalate" else "✋ Claim this lead"
    return {"inline_keyboard": [[{"text": label, "callback_data": f"claim:{enquiry['id']}"}]]}


def post(enquiry: dict, chat: str, kind: str, now: datetime, banner: str = "") -> bool:
    """Posts one alert. Returns False if that chat isn't configured."""
    chat_id = CHATS.get(chat)
    if not chat_id and TELEGRAM_BOT_TOKEN:
        return False
    text = (banner + "\n\n" if banner else "") + handoff.render_telegram(handoff.build_note(enquiry))
    loud = in_alert_hours(now) or (enquiry["decision"] == "Escalate" and ROUTING["complaints_ignore_alert_hours"])
    params = {
        "chat_id": chat_id or f"<{chat} chat>",
        "text": text,
        "parse_mode": "HTML",
        "disable_notification": not loud,      # at night: delivered, but no buzz
        "link_preview_options": {"is_disabled": True},
    }
    if enquiry["decision"] in ("Book", "Escalate"):
        params["reply_markup"] = _button(enquiry)
    result = api("sendMessage", **params)
    sent_at = now.astimezone(IST).isoformat(timespec="seconds")
    db.record_alert(enquiry["id"], chat, chat_id, result.get("message_id"), kind, sent_at, text)
    db.add_messaging_cost(enquiry["id"], ASSUMPTIONS["costs"]["variable"]["message_inr_per_alert"])
    db.log_event(enquiry["id"], "alert_sent" if kind == "first" else kind, f"{chat} · {'loud' if loud else 'silent'}", sent_at)
    return True


def route_new(enquiry_id: int, now: datetime | None = None):
    """Called by the pipeline once per new enquiry."""
    now = now or datetime.now(IST)
    e = db.get_enquiry(enquiry_id)
    decision = e["decision"]

    if decision == "Escalate":
        post(e, "urgent", "first", now, "🚨 <b>Existing client: call back now</b>")
    elif decision == "Book":
        post(e, "designers", "first", now)
        priority = PRIORITY_FLAGS & set(e["flags"])
        if priority:
            post(e, "urgent", "first", now, "👀 <b>FYI, priority lead:</b> " + ", ".join(sorted(priority)))
    elif decision == "Ask":
        post(e, "frontdesk", "first", now, "📝 <b>Front desk: one question still open</b>")
        if "repeat_caller_no_followup" in e["flags"]:   # T16: never let a repeat caller slip twice
            post(e, "urgent", "first", now, "👀 <b>FYI: repeat caller, never followed up.</b> Front desk is on it.")

    if e["pricing_violation"]:
        post(e, "frontdesk", "first", now, "⚠️ <b>Pricing guardrail tripped</b>: please read the transcript")


# ── Claiming ─────────────────────────────────────────────────────────────────
def _who(user: dict) -> str:
    name = " ".join(p for p in (user.get("first_name"), user.get("last_name")) if p)
    return name or user.get("username") or str(user.get("id"))


def apply_claim(enquiry_id: int, who: str, now: datetime | None = None) -> tuple[bool, str]:
    """Used by the Telegram button AND the dashboard. Returns (claimed_now, message)."""
    now = now or datetime.now(IST)
    at_iso = now.astimezone(IST).isoformat(timespec="seconds")
    if not db.claim(enquiry_id, who, at_iso):
        e = db.get_enquiry(enquiry_id)
        return False, f"Already claimed by {e['claimed_by']}" if e else "Not found"

    e = db.get_enquiry(enquiry_id)
    minutes = (now - datetime.fromisoformat(e["received_at"])).total_seconds() / 60
    db.log_event(enquiry_id, "claimed", f"{who} · {minutes:.0f} min after the call", at_iso)

    stamp = f"\n\n✅ <b>Claimed by {escape(who)}</b> at {now.astimezone(IST):%I:%M %p} ({minutes:.0f} min after the call)"
    for alert in db.alerts_for(enquiry_id):
        if alert["message_id"] or not TELEGRAM_BOT_TOKEN:
            try:
                api("editMessageText", chat_id=alert["chat_id"], message_id=alert["message_id"],
                    text=alert["text"] + stamp, parse_mode="HTML",
                    link_preview_options={"is_disabled": True}, reply_markup={"inline_keyboard": []})
            except RuntimeError as exc:   # e.g. message too old to edit; the claim itself still stands
                db.log_event(enquiry_id, "error", str(exc), at_iso)
    return True, "It's yours. Please call them now." if e["decision"] == "Book" else "Thanks, logged as acknowledged."


def handle_update(update: dict) -> dict:
    """Processes one Telegram update (from the webhook or from polling)."""
    cq = update.get("callback_query")
    if not cq or not str(cq.get("data", "")).startswith("claim:"):
        return {"ignored": True}

    chat_id = str((cq.get("message") or {}).get("chat", {}).get("id"))
    if chat_id not in {c for c in CHATS.values() if c}:
        api("answerCallbackQuery", callback_query_id=cq["id"], text="Not allowed from this chat.")
        return {"ignored": True, "reason": "unknown chat"}

    enquiry_id = int(cq["data"].split(":", 1)[1])
    claimed, message = apply_claim(enquiry_id, _who(cq.get("from") or {}))
    api("answerCallbackQuery", callback_query_id=cq["id"], text=message, show_alert=not claimed)
    return {"claimed": claimed, "message": message}

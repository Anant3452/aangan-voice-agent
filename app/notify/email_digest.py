"""
Daily email digest: the written record, and the fallback if Telegram is down.

Sent each morning for the previous day. It contains:
  - the day's numbers
  - "Needs attention": anything unclaimed, Ask follow-ups, review items, nurture leads
  - every booked lead with its FULL handoff note (so designers can work from email alone)
  - escalations, and declines with reasons

No SMTP settings in .env  →  written to data/digests/ instead of sent.
"""
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
from html import escape
from zoneinfo import ZoneInfo

from .. import db, handoff
from ..config import (ASSUMPTIONS, DB_PATH, DIGEST_FROM, DIGEST_TO, SMTP_HOST, SMTP_PASSWORD,
                      SMTP_PORT, SMTP_USER)

IST = ZoneInfo(ASSUMPTIONS["business"]["timezone"])


def _claim_minutes(e: dict) -> float | None:
    if not e.get("claimed_at"):
        return None
    return (datetime.fromisoformat(e["claimed_at"]) - datetime.fromisoformat(e["received_at"])).total_seconds() / 60


def _line(e: dict) -> str:
    out = e.get("agent_output") or {}
    where = (out.get("project") or {}).get("location_text") or "location n/a"
    return f"#{e['id']} {e.get('caller_name') or 'Unknown'} · {where} · {e.get('reason') or ''}"


def build(day: datetime) -> tuple[str, str, str]:
    """Returns (subject, plain_text, html) for the IST calendar day containing `day`."""
    start = day.astimezone(IST).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    rows = [e for e in db.enquiries_between(start.isoformat(), end.isoformat()) if e["reason_code"] != "not_a_lead"]

    by = {d: [e for e in rows if e["decision"] == d] for d in ("Book", "Ask", "Decline", "Escalate")}
    claim_times = [m for m in (_claim_minutes(e) for e in by["Book"]) if m is not None]
    open_leads = db.unclaimed(("Book", "Escalate"))

    stats = [
        ("Enquiries", len(rows)),
        ("After hours", sum(e["after_hours"] for e in rows)),
        ("Consultations booked", len(by["Book"])),
        ("Need a follow-up (Ask)", len(by["Ask"])),
        ("Declined", len(by["Decline"])),
        ("Escalations", len(by["Escalate"])),
        ("Avg call → claim", f"{sum(claim_times) / len(claim_times):.0f} min" if claim_times else "n/a"),
        ("Still unclaimed (all days)", len(open_leads)),
        ("Pricing guardrail hits", sum(e["pricing_violation"] for e in rows)),
    ]

    attention = (
        [("UNCLAIMED", e) for e in open_leads]
        + [("ASK", e) for e in by["Ask"] if "continued_in_later_call" not in e["flags"]]
        + [("REVIEW", e) for e in rows if e["needs_review"]]
        + [("NURTURE", e) for e in rows if "nurture_later" in e["flags"]]
    )

    subject = (f"Aangan enquiries · {start:%a %d %b}: {len(rows)} calls, "
               f"{len(by['Book'])} booked, {len(by['Escalate'])} escalated")

    # ── plain text ──
    t = [subject, "=" * len(subject), ""]
    t += [f"{k}: {v}" for k, v in stats] + [""]
    t += ["NEEDS ATTENTION"] + ([f"  [{tag}] {_line(e)}" for tag, e in attention] or ["  Nothing. 🎉"]) + [""]
    t += ["ESCALATIONS"] + ([f"  {_line(e)} · acknowledged by {e['claimed_by'] or 'NOBODY YET'}"
                             for e in by["Escalate"]] or ["  None"]) + [""]
    t += ["DECLINED"] + ([f"  {_line(e)} [{e['reason_code']}]" for e in by["Decline"]] or ["  None"]) + [""]
    t += ["BOOKED: full handoff notes", ""]
    for e in by["Book"]:
        t += [handoff.render_text(handoff.build_note(e)),
              f"Claimed by: {e['claimed_by'] or 'NOT CLAIMED'}", "-" * 60]
    text = "\n".join(t)

    # ── html ──
    def table(items):
        return "<table cellpadding='4' style='border-collapse:collapse'>" + "".join(
            f"<tr><td style='color:#666'>{escape(str(k))}</td><td><b>{escape(str(v))}</b></td></tr>" for k, v in items
        ) + "</table>"

    def lst(items):
        return "<ul>" + ("".join(f"<li>{escape(i)}</li>" for i in items) or "<li>None</li>") + "</ul>"

    html = (
        f"<div style='font-family:system-ui,sans-serif;max-width:720px'><h2>{escape(subject)}</h2>"
        + table(stats)
        + "<h3>Needs attention</h3>" + lst([f"[{tag}] {_line(e)}" for tag, e in attention])
        + "<h3>Escalations</h3>" + lst([f"{_line(e)} · acknowledged by {e['claimed_by'] or 'NOBODY YET'}"
                                         for e in by["Escalate"]])
        + "<h3>Declined</h3>" + lst([f"{_line(e)} [{e['reason_code']}]" for e in by["Decline"]])
        + "<h3>Booked: full handoff notes</h3>"
        + "".join(f"<pre style='white-space:pre-wrap;background:#f6f6f6;padding:8px'>"
                  f"{escape(handoff.render_text(handoff.build_note(e)))}\nClaimed by: "
                  f"{escape(e['claimed_by'] or 'NOT CLAIMED')}</pre>" for e in by["Book"])
        + "</div>"
    )
    return subject, text, html


def send(day: datetime) -> str:
    subject, text, html = build(day)
    if not (SMTP_HOST and SMTP_USER and DIGEST_TO):
        folder = DB_PATH.parent / "digests"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"digest_{day.astimezone(IST):%Y-%m-%d}.html"
        path.write_text(html, encoding="utf-8")
        (folder / path.name.replace(".html", ".txt")).write_text(text, encoding="utf-8")
        return f"saved {path} (SMTP not configured)"

    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, DIGEST_FROM, ", ".join(DIGEST_TO)
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
        smtp.starttls()
        smtp.login(SMTP_USER, SMTP_PASSWORD)
        smtp.send_message(msg)
    return f"emailed to {', '.join(DIGEST_TO)}"


if __name__ == "__main__":
    # Preview any day's digest:  .venv/bin/python -m app.notify.email_digest 2026-09-22
    import sys
    target = datetime.fromisoformat(sys.argv[1]).replace(tzinfo=IST) if len(sys.argv) > 1 else datetime.now(IST)
    print(build(target)[1])

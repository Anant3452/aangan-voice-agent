"""
The designer handoff note.

Built only from what the agent captured, so the designer's first call starts
where the phone call ended. A "Covered on the call" line tells the designer
what NOT to ask again, and an "Open questions" line tells them what to ask.

Two renderings of the same note:
  render_text()      plain text   (email digest, logs)
  render_telegram()  Telegram HTML (bold labels, safe escaping)
"""
from datetime import datetime
from html import escape

from . import links

FLAG_LABELS = {
    "vip_referral": "⭐ Personal connection to Nikhil",
    "repeat_caller_no_followup": "🔴 PRIORITY: called before and was never followed up. Call today",
    "frustrated_caller": "😟 Caller was frustrated; open with an apology",
    "acting_on_behalf": "👥 Caller is acting for the owners",
    "large_project": "📐 Large project; Nikhil to review",
    "rented_property": "🏠 Rented: nothing structural",
    "structural_request": "🧱 Asked about structural work (we told them we don't do it)",
    "site_visit_requested": "📍 Wants a site visit",
    "service_area_edge": "🗺️ Edge of service area; confirm before the visit",
    "timeline_reset_by_caller": "📅 Original deadline was too tight; caller agreed a later finish",
    "pricing_asked": "💬 Asked about pricing; was told the designer will cover it",
    "human_callback_requested": "☎️ Asked for a human callback",
    "ai_disclosure_asked": "🤖 Asked if they were talking to a bot",
    "after_hours": "🌙 Called outside office hours",
    "language_switch": "🗣️ Prefers Hindi/Hinglish",
    "dropped_call": "📵 Call dropped part-way",
}

DECISION_TITLES = {
    "Book": "New qualified lead: consultation booked",
    "Ask": "Enquiry needs one more answer (front desk to follow up)",
    "Escalate": "URGENT: existing client needs a senior callback",
    "Decline": "Declined enquiry (for the record)",
}


def _fmt_area(project: dict) -> str | None:
    sqft = project.get("carpet_area_sqft")
    if not sqft:
        return None
    basis = project.get("area_basis")
    suffix = " carpet" if basis == "carpet" else " built-up" if basis == "built_up" else " (carpet/built-up not confirmed)"
    return f"{sqft:,.0f} sq ft{suffix}"


def _fmt_phone(number: str | None) -> str | None:
    """'9800000014' → '+91 98000 00014' (tap-to-call friendly)."""
    if number and len(number) == 10 and number.isdigit():
        return f"+91 {number[:5]} {number[5:]}"
    return number


def _fmt_time(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%a %d %b, %I:%M %p").replace(" 0", " ")


def _join(*parts) -> str | None:
    text = " · ".join(str(p) for p in parts if p)
    return text or None


def _covered_and_open(out: dict) -> tuple[list[str], list[str]]:
    """What the caller already told us, and what's still open, so nobody asks twice."""
    project, criteria = out.get("project") or {}, out.get("criteria") or {}
    covered, open_q = [], []
    checks = [
        ("location", project.get("location_text") or project.get("locality")),
        ("property type & size", project.get("bhk") or project.get("carpet_area_sqft") or project.get("property_type")),
        ("scope", project.get("scope_summary") or project.get("scope_rooms")),
        ("timeline", project.get("timeline_text")),
        ("site status", project.get("site_status") not in (None, "unknown")),
        ("who decides", (criteria.get("c5_decision_maker") or {}).get("result") == "pass"),
        ("how they found us", (out.get("source") or {}).get("type") not in (None, "unknown")),
    ]
    for label, known in checks:
        (covered if known else open_q).append(label)
    if (out.get("budget") or {}).get("volunteered"):
        covered.append("budget (volunteered)")
    open_q.extend(out.get("uncertainties") or [])
    return covered, open_q


def build_note(record: dict) -> dict:
    """record = a row from the enquiries table (agent_output already parsed)."""
    out = record.get("agent_output") or {}
    caller = out.get("caller") or {}
    source = out.get("source") or {}
    project = out.get("project") or {}
    budget = out.get("budget") or {}
    consult = out.get("consultation") or {}
    esc = out.get("escalation") or {}
    c5 = (out.get("criteria") or {}).get("c5_decision_maker") or {}
    covered, open_q = _covered_and_open(out)

    referrer = source.get("referrer_name")
    note = {
        "id": record["id"],
        "decision": record["decision"],
        "title": DECISION_TITLES.get(record["decision"], record["decision"]),
        "received_at": _fmt_time(record["received_at"]),
        "name": caller.get("name") or "Not given",
        "contact": _fmt_phone(record.get("caller_number")) or caller.get("phone") or "Withheld",
        "source": _join(source["type"].replace("_", " ").title() if source.get("type") not in (None, "unknown") else None,
                        f"referred by {referrer}" if referrer else None, source.get("detail")) or "Not mentioned",
        "location": _join(project.get("location_text"), (project.get("zone") or "").replace("_", " ").upper() or None)
                    or "Not given",
        "property": _join(project.get("segment", "").title() if project.get("segment") else None,
                          (project.get("property_type") or "").replace("_", " ") or None,
                          project.get("bhk"), _fmt_area(project)) or "Not given",
        "scope": _join(project.get("scope_summary"),
                       ", ".join(project.get("scope_rooms") or []) or None,
                       f"site: {project['site_status'].replace('_', ' ')}" if project.get("site_status") else None,
                       project.get("ownership") if project.get("ownership") == "rented" else None)
                 or "Not given",
        "timeline": _join(project.get("timeline_text"),
                          f"site available {project['site_available_from']}" if project.get("site_available_from") else None)
                    or "Not given",
        "decision_maker": _join({"pass": "Yes", "unclear": "Not confirmed", "fail": "No"}.get(c5.get("result")), c5.get("evidence"),
                                f"acting for {caller['acting_for']}" if caller.get("acting_for") else None)
                          or "Not discussed",
        # Budget is shown ONLY if the caller raised it. We never asked.
        "budget": budget.get("caller_words") if budget.get("volunteered") else None,
        "uncertainties": open_q,
        "covered": covered,
        "slot": _join(consult.get("slot_text"), (consult.get("mode") or "").replace("_", " ") or None,
                      f"attending: {consult['attendees']}" if consult.get("attendees") else None,
                      f"caller's constraint: {consult['caller_constraints']}" if consult.get("caller_constraints") else None)
                or "No slot agreed",
        "brief": out.get("designer_brief"),
        "flags": [FLAG_LABELS[f] for f in record.get("flags") or [] if f in FLAG_LABELS],
        "review": record.get("review_reasons") or [],
        "transcript_link": links.transcript_url(record["id"]),
        "escalation": esc or None,
    }
    return note


# ── Renderers ────────────────────────────────────────────────────────────────
def _rows(note: dict) -> list[tuple[str, str]]:
    if note["decision"] == "Escalate" and note["escalation"]:
        e = note["escalation"]
        return [
            ("Client", note["name"]),
            ("Contact", note["contact"]),
            ("Project", e.get("project_location") or note["location"]),
            ("Designer on project", e.get("assigned_designer") or "Not given"),
            ("Issue", e.get("issue_summary") or "See transcript"),
            ("Already tried", e.get("already_tried") or "Not given"),
            ("Wants callback from", e.get("callback_requested_from") or "Senior person"),
            ("Agent promised", e.get("promised_callback") or "A senior callback"),
        ]
    rows = [
        ("Name", note["name"]),
        ("Contact", note["contact"]),
        ("Source", note["source"]),
        ("Location", note["location"]),
        ("Property", note["property"]),
        ("Scope", note["scope"]),
        ("Timeline", note["timeline"]),
        ("Decision-maker", note["decision_maker"]),
    ]
    if note["budget"]:
        rows.append(("Budget (caller's words)", note["budget"]))
    rows += [
        ("Consultation", note["slot"]),
        ("Covered on the call (don't re-ask)", ", ".join(note["covered"]) or "Nothing"),
        ("Open questions", "; ".join(note["uncertainties"]) or "None"),
    ]
    return rows


def render_text(note: dict) -> str:
    lines = [f"{note['title']}  (#{note['id']}, {note['received_at']})", ""]
    lines += [f"⚠️ Needs review: {r}" for r in note["review"]]
    lines += note["flags"]
    if note["review"] or note["flags"]:
        lines.append("")
    lines += [f"{label}: {value}" for label, value in _rows(note)]
    if note["brief"]:
        lines += ["", f"In short: {note['brief']}"]
    lines += ["", f"Transcript: {note['transcript_link']}"]
    return "\n".join(lines)


def render_telegram(note: dict) -> str:
    """Telegram 'HTML' parse mode allows only a few tags; everything else is escaped."""
    lines = [f"<b>{escape(note['title'])}</b>  #{note['id']}", ""]
    lines += [f"⚠️ <b>Needs review:</b> {escape(r)}" for r in note["review"]]
    lines += [escape(f) for f in note["flags"]]
    if note["review"] or note["flags"]:
        lines.append("")
    lines += [f"<b>{escape(label)}:</b> {escape(str(value))}" for label, value in _rows(note)]
    if note["brief"]:
        lines += ["", f"<i>{escape(note['brief'])}</i>"]
    lines += ["", f'<a href="{escape(note["transcript_link"])}">Full transcript</a>']
    return "\n".join(lines)

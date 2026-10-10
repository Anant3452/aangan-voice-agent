"""
The web server. Routes only — the logic lives in pipeline.py and friends.

Run locally:  .venv/bin/uvicorn app.main:app --reload
On Vercel:    api/index.py imports `app` from here.
"""
import asyncio
import csv
import io
import json
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

from . import db, handoff, links, metrics, pipeline, scheduler
from . import demo as demo_data
from .channels import vaani_adapter
from .channels.base import AdapterError
from .config import (ASSUMPTIONS, CRON_TOKEN, DASHBOARD_PASSWORD, DB_PATH, DEMO_SEED, ON_VERCEL, ROOT,
                     SCHEDULER_ENABLED, TELEGRAM_WEBHOOK_SECRET, WEBHOOK_TOKEN)
from .notify import telegram

IST = ZoneInfo(ASSUMPTIONS["business"]["timezone"])


async def _scheduler_loop():
    while True:
        await run_in_threadpool(scheduler.tick)
        await asyncio.sleep(ASSUMPTIONS["routing"]["scheduler_interval_seconds"])


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_db()
    task = asyncio.create_task(_scheduler_loop()) if SCHEDULER_ENABLED else None
    yield
    if task:
        task.cancel()


app = FastAPI(title="Aangan Studio — enquiry backend", lifespan=lifespan)


@app.middleware("http")
async def _demo_seed(request: Request, call_next):
    """On Vercel the database starts empty on every new instance; load T01–T20 once."""
    if DEMO_SEED:
        await run_in_threadpool(demo_data.seed_if_empty)
    return await call_next(request)


_basic = HTTPBasic(auto_error=False)


def require_login(creds: HTTPBasicCredentials | None = Depends(_basic)):
    """Browser login for the dashboard and read APIs. Skipped if DASHBOARD_PASSWORD is blank."""
    if not DASHBOARD_PASSWORD:
        return
    if not creds or not secrets.compare_digest(creds.password, DASHBOARD_PASSWORD):
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})


LOGIN = [Depends(require_login)]


def _check_token(request: Request):
    """Our own shared secret (?token=...). Not a Vaani feature — works with any platform that lets you set a URL."""
    if WEBHOOK_TOKEN and request.query_params.get("token") != WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="Bad or missing token")


@app.get("/health")
def health():
    return {"ok": True, "vercel": ON_VERCEL, "demo_seed": DEMO_SEED, "scheduler": SCHEDULER_ENABLED}


# ── Phone (Vaani) ────────────────────────────────────────────────────────────
@app.post("/webhooks/vaani")
async def vaani_webhook(request: Request):
    _check_token(request)
    payload = await request.json()
    try:
        enquiry = vaani_adapter.to_enquiry(payload)
    except AdapterError as exc:
        db.log_event(None, "error", f"vaani adapter: {exc}")
        # 422 tells the sender the payload was understood as invalid — don't retry forever
        raise HTTPException(status_code=422, detail=str(exc))
    result = await run_in_threadpool(pipeline.process, enquiry)   # Telegram calls are blocking
    return JSONResponse(result)


@app.post("/webhooks/vaani/capture")
async def vaani_capture(request: Request):
    """Point Vaani here for ONE test call to see its real payload. Saved next to the database."""
    _check_token(request)
    payload = await request.json()
    path = DB_PATH.parent / f"captured_{datetime.now():%Y%m%d_%H%M%S}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    # On Vercel /tmp disappears, so also echo it back in the response
    return {"saved_to": str(path), "payload": payload}


# ── Telegram button taps ──────────────────────────────────────────────────────
@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    # Telegram sends back the secret we gave it in setWebhook (real Telegram feature).
    if TELEGRAM_WEBHOOK_SECRET and request.headers.get("X-Telegram-Bot-Api-Secret-Token") != TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(status_code=401)
    update = await request.json()
    await run_in_threadpool(telegram.handle_update, update)
    return {"ok": True}   # always 200, or Telegram keeps retrying


# ── Scheduler trigger (for hosts where the in-process loop can't run) ────────
@app.api_route("/tasks/tick", methods=["GET", "POST"])
def tasks_tick(request: Request):
    """Point an external cron (e.g. cron-job.org, every minute) here: /tasks/tick?token=CRON_TOKEN."""
    if not CRON_TOKEN or request.query_params.get("token") != CRON_TOKEN:
        raise HTTPException(status_code=401, detail="Set CRON_TOKEN and pass ?token=")
    scheduler.tick()
    return {"ok": True}


class ClaimRequest(BaseModel):
    by: str


@app.post("/api/enquiries/{enquiry_id}/claim", dependencies=LOGIN)
def claim(enquiry_id: int, body: ClaimRequest):
    """Claim from the dashboard, for anyone not on Telegram (and for demos)."""
    claimed, message = telegram.apply_claim(enquiry_id, body.by.strip() or "Unknown")
    return {"claimed": claimed, "message": message}


# ── Future channels (planned, not built) ─────────────────────────────────────
@app.post("/webhooks/whatsapp")
@app.post("/webhooks/webform")
def not_built():
    raise HTTPException(status_code=501, detail="Planned channel — see app/channels/*_adapter.py")


# ── Read APIs ────────────────────────────────────────────────────────────────
@app.get("/api/enquiries", dependencies=LOGIN)
def list_enquiries(limit: int = 100):
    rows = db.list_enquiries(limit)
    for r in rows:
        r.pop("raw_payload", None)
    return rows


@app.get("/api/enquiries/{enquiry_id}", dependencies=LOGIN)
def enquiry_detail(enquiry_id: int):
    """Everything the dashboard's detail panel shows for one enquiry."""
    row = db.get_enquiry(enquiry_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    row.pop("raw_payload", None)
    out = row.get("agent_output") or {}
    return {
        "enquiry": row,
        "criteria": out.get("criteria") or {},
        "note": handoff.render_text(handoff.build_note(row)) if row["decision"] != "Decline" else None,
        "events": db.events_for(enquiry_id),
        "transcript_url": links.transcript_url(enquiry_id),
    }


@app.get("/api/enquiries/{enquiry_id}/events", dependencies=LOGIN)
def enquiry_events(enquiry_id: int):
    """The full timeline of one enquiry: received → alerted → re-alerted → claimed."""
    return db.events_for(enquiry_id)


@app.get("/api/export.csv", dependencies=LOGIN)
def export_csv():
    """Everything in one spreadsheet, so nobody ever copies numbers by hand."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=db.EXPORT_COLUMNS)
    writer.writeheader()
    writer.writerows(db.export_rows())
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=aangan_enquiries.csv"})


@app.post("/api/demo/reset", dependencies=LOGIN)
def demo_reset():
    """Put the demo data back to its starting state (e.g. after a class demo with claims)."""
    removed = demo_data.reset()
    return {"removed": removed, "added": demo_data.seed()}


@app.get("/enquiries/{enquiry_id}/transcript", response_class=PlainTextResponse)
def transcript(enquiry_id: int, k: str = ""):
    """The 'transcript link' in each designer handoff note. Needs the signed ?k= from links.py."""
    row = db.get_enquiry(enquiry_id)
    if not row or not links.is_valid(enquiry_id, k):
        raise HTTPException(status_code=404, detail="Not found")
    header = f"Enquiry #{row['id']} · {row['channel']} · {row['received_at']} · {row['decision']}\n\n"
    body = "\n".join(f"{t['speaker'].title()}: {t['text']}" for t in row["transcript"])
    return header + body


# ── Dashboard ────────────────────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse("/dashboard")


@app.get("/dashboard", dependencies=LOGIN, include_in_schema=False)
def dashboard():
    return FileResponse(ROOT / "dashboard" / "index.html")


@app.get("/api/metrics", dependencies=LOGIN)
def api_metrics(period: str = "all", demo: bool = True, volume: int | None = None):
    """period: all | 7d | 30d | mtd (month to date)."""
    now = datetime.now(IST)
    starts = {
        "7d": now - timedelta(days=7),
        "30d": now - timedelta(days=30),
        "mtd": now.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
    }
    start = starts.get(period)
    end = now + timedelta(minutes=1)
    return metrics.compute(start.isoformat(timespec="seconds") if start else None,
                           end.isoformat(timespec="seconds"), demo, volume)

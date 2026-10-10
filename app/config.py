"""Loads secrets from .env and tunable numbers from config/assumptions.yaml."""
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

with open(ROOT / "config" / "assumptions.yaml", encoding="utf-8") as fh:
    ASSUMPTIONS = yaml.safe_load(fh)


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


# Vercel sets VERCEL=1. Its filesystem is read-only except /tmp, and nothing
# runs between requests, so the database lives in /tmp and the loop is off.
ON_VERCEL = env("VERCEL") == "1"

DB_PATH = Path(env("DB_PATH", "/tmp/aangan.db" if ON_VERCEL else "data/aangan.db"))
if not DB_PATH.is_absolute():
    DB_PATH = ROOT / DB_PATH
_vercel_host = env("VERCEL_PROJECT_PRODUCTION_URL")   # set automatically by Vercel
PUBLIC_BASE_URL = env("PUBLIC_BASE_URL", f"https://{_vercel_host}" if _vercel_host else "http://localhost:8000")
WEBHOOK_TOKEN = env("WEBHOOK_TOKEN")  # if set, webhooks must include ?token=<value>
LINK_SECRET = env("LINK_SECRET", "dev-only-change-me")  # signs transcript links
DEMO_SEED = env("DEMO_SEED", "true" if ON_VERCEL else "false").lower() == "true"

TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN")
TELEGRAM_DESIGNERS_CHAT_ID = env("TELEGRAM_DESIGNERS_CHAT_ID")
TELEGRAM_URGENT_CHAT_ID = env("TELEGRAM_URGENT_CHAT_ID")
TELEGRAM_FRONTDESK_CHAT_ID = env("TELEGRAM_FRONTDESK_CHAT_ID")
TELEGRAM_WEBHOOK_SECRET = env("TELEGRAM_WEBHOOK_SECRET")

SMTP_HOST = env("SMTP_HOST")
SMTP_PORT = int(env("SMTP_PORT", "587"))
SMTP_USER = env("SMTP_USER")
SMTP_PASSWORD = env("SMTP_PASSWORD")
DIGEST_FROM = env("DIGEST_FROM") or SMTP_USER
DIGEST_TO = [a.strip() for a in env("DIGEST_TO").split(",") if a.strip()]

SCHEDULER_ENABLED = env("SCHEDULER_ENABLED", "false" if ON_VERCEL else "true").lower() == "true"
CRON_TOKEN = env("CRON_TOKEN")  # protects /tasks/tick (external cron when the in-process loop is off)

DASHBOARD_PASSWORD = env("DASHBOARD_PASSWORD")  # blank = no login (fine on your laptop, NOT for real data)

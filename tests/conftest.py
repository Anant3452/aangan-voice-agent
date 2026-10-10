"""Every test run gets its own empty database, dry-run Telegram, no background loop, no demo seeding."""
import os
import tempfile

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["WEBHOOK_TOKEN"] = ""
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["TELEGRAM_BOT_TOKEN"] = ""   # tests always run in dry-run mode
os.environ["DEMO_SEED"] = "false"
os.environ.pop("VERCEL", None)

"""
Telegram setup helpers.

  python -m app.notify.telegram_cli chats        # list chats the bot has seen → copy their IDs into .env
  python -m app.notify.telegram_cli set-webhook  # tell Telegram to send button taps to PUBLIC_BASE_URL
  python -m app.notify.telegram_cli poll         # local testing without a public URL: fetch button taps yourself
"""
import sys
import time

from ..config import PUBLIC_BASE_URL, TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET
from . import telegram


def chats():
    telegram.api("deleteWebhook")   # getUpdates doesn't work while a webhook is set; run set-webhook again after
    seen = {}
    for update in telegram.api("getUpdates", timeout=0):
        msg = update.get("message") or update.get("my_chat_member") or {}
        chat = msg.get("chat")
        if chat:
            seen[chat["id"]] = chat.get("title") or chat.get("username") or chat.get("first_name")
    if not seen:
        print("No chats yet. Add the bot to your groups and send any message in each, then run this again.")
    for chat_id, name in seen.items():
        print(f"{chat_id}\t{name}")


def set_webhook():
    url = f"{PUBLIC_BASE_URL}/telegram/webhook"
    params = {"url": url, "allowed_updates": ["callback_query"]}
    if TELEGRAM_WEBHOOK_SECRET:
        params["secret_token"] = TELEGRAM_WEBHOOK_SECRET
    telegram.api("setWebhook", **params)
    print(f"Webhook set to {url}")


def poll():
    telegram.api("deleteWebhook")
    print("Polling for button taps. Ctrl+C to stop.")
    offset = None
    while True:
        for update in telegram.api("getUpdates", offset=offset, timeout=30, allowed_updates=["callback_query"]):
            offset = update["update_id"] + 1
            print(telegram.handle_update(update))
        time.sleep(1)


if __name__ == "__main__":
    if not TELEGRAM_BOT_TOKEN:
        sys.exit("Set TELEGRAM_BOT_TOKEN in .env first.")
    {"chats": chats, "set-webhook": set_webhook, "poll": poll}[sys.argv[1] if len(sys.argv) > 1 else "chats"]()

"""
WhatsApp → Enquiry   (NOT BUILT — out of scope for this phase)

How it would plug in:
  - The WhatsApp Business API posts each incoming message to /webhooks/whatsapp.
  - A WhatsApp agent (same rubric, same Part B output) chats with the customer.
  - When the conversation goes quiet or the agent books/declines, this adapter
    builds an Enquiry with channel="whatsapp", duration_sec=None,
    transcript = the message thread, agent_output = the same JSON schema.
  - Everything downstream (rules check, handoff note, Telegram, dashboard) is reused.

Cases from the enquiries file it must handle: W01 (after-hours referral),
W03 (Hindi), W08 (repeat contact, frustrated), W09 (photos attached → store media links).
"""
from .base import Enquiry


def to_enquiry(payload: dict) -> Enquiry:
    raise NotImplementedError("WhatsApp channel is planned, not built. See module docstring.")

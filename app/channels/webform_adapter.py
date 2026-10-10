"""
Website form → Enquiry   (NOT BUILT — out of scope for this phase)

How it would plug in:
  - The website form POSTs to /webhooks/webform.
  - The form fields (Project type, Location, Carpet area, Timeline, Budget,
    How did you find us) already map almost 1:1 onto agent_output.project,
    .budget and .source — so a small LLM step (or plain rules) fills the five
    criteria directly from the form, with no conversation.
  - Anything left 'unclear' (e.g. F04: "Location: Pune, Budget: reasonable")
    becomes decision "Ask" → the phone agent places an OUTBOUND call to ask the
    one missing question, which then flows back in through the Vaani adapter.
"""
from .base import Enquiry


def to_enquiry(payload: dict) -> Enquiry:
    raise NotImplementedError("Web form channel is planned, not built. See module docstring.")

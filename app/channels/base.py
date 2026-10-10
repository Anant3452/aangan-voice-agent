"""
The one shape every channel is converted into.

Vaani (phone) today; WhatsApp and the web form later. Each channel gets an
adapter that turns its raw payload into an `Enquiry`. Everything after that
(rules check, storage, handoff, Telegram, dashboard) only ever sees `Enquiry`,
so adding a channel never touches the rest of the pipeline.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Turn:
    speaker: str  # "agent" or "caller"
    text: str


@dataclass
class Enquiry:
    channel: str                      # "phone" | "whatsapp" | "webform"
    external_id: str                  # the platform's own ID — used to ignore duplicate deliveries
    received_at: datetime             # timezone-aware
    caller_number: Optional[str]
    duration_sec: Optional[int]       # None for non-voice channels
    transcript: list[Turn]
    agent_output: Optional[dict]      # the structured JSON (agent/output_schema.json)
    answer_delay_sec: Optional[int] = None   # seconds from first ring/message to first reply
    recording_url: Optional[str] = None
    platform_cost_inr: Optional[float] = None  # if the platform reports its own cost per call
    raw_payload: dict = field(default_factory=dict)

    def transcript_text(self) -> str:
        return "\n".join(f"{t.speaker.title()}: {t.text}" for t in self.transcript)


class AdapterError(ValueError):
    """Raised when a payload can't be turned into an Enquiry."""

"""
Pricing safety net.

The prompt forbids the agent from saying any price. Prompts are not guarantees,
so after every call we scan what the AGENT said (never the caller) for anything
that looks like a price. A hit raises a compliance flag that Nikhil sees on the
dashboard and in the daily digest.
"""
import re

from .channels.base import Turn

PRICE_PATTERNS = [
    (r"₹\s*\d", "rupee symbol with a number"),
    (r"\brs\.?\s*\d", "Rs with a number"),
    (r"\brupees?\b", "the word rupees"),
    (r"\b(lakh|lakhs|lac|lacs|crore|crores)\b", "lakh/crore"),
    (r"\bper\s*(sq\.?\s*ft|square\s*f(oo|ee)t|sqft)\b", "per sq ft"),
    (r"\b\d[\d,]*\s*(k|thousand)\b", "a thousands figure"),
    (r"\b(starting|starts|start)\s+(at|from)\b", "'starting at/from'"),
    (r"\b(costs?|typically|usually)\s+(around|about|roughly)\b", "'costs around'"),
]

# Not a price, but "free consultation" is unconfirmed (contradictions.md #8)
SOFT_PATTERNS = [
    (r"\bfree\b", "said 'free' (unconfirmed with Nikhil)"),
]


def scan_agent_speech(transcript: list[Turn]) -> dict:
    violations, notes = [], []
    for turn in transcript:
        if turn.speaker != "agent":
            continue
        text = turn.text.lower()
        for pattern, label in PRICE_PATTERNS:
            if re.search(pattern, text):
                violations.append({"rule": label, "said": turn.text})
                break
        for pattern, label in SOFT_PATTERNS:
            if re.search(pattern, text):
                notes.append({"rule": label, "said": turn.text})
    return {"pricing_violation": bool(violations), "violations": violations, "notes": notes}

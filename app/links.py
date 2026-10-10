"""
Signed links, so a transcript URL posted in Telegram can't be guessed by
changing the number in it. The signature is an HMAC of the enquiry id.
"""
import hashlib
import hmac

from .config import LINK_SECRET, PUBLIC_BASE_URL


def _sign(enquiry_id: int) -> str:
    return hmac.new(LINK_SECRET.encode(), str(enquiry_id).encode(), hashlib.sha256).hexdigest()[:16]


def transcript_url(enquiry_id: int) -> str:
    return f"{PUBLIC_BASE_URL}/enquiries/{enquiry_id}/transcript?k={_sign(enquiry_id)}"


def is_valid(enquiry_id: int, signature: str) -> bool:
    return hmac.compare_digest(_sign(enquiry_id), signature or "")

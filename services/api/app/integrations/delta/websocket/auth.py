"""HMAC signing for Delta Exchange WebSocket ``key-auth`` messages.

Per the Delta documentation the signature is the hex digest of
``GET + timestamp + "/live"`` signed with the API secret:

``signature = HMAC_SHA256(api_secret, "GET" + timestamp + "/live")``
"""

import hashlib
import hmac


def sign_key_auth(api_secret: str, timestamp: str) -> str:
    """Build the HMAC-SHA256 signature for a ``key-auth`` message.

    Args:
        api_secret: The Delta API secret.
        timestamp: The current Unix timestamp as a string; must be the
            same value sent in the ``key-auth`` payload.

    Returns:
        The hex-encoded HMAC-SHA256 digest.
    """
    message = f"GET{timestamp}/live"
    return hmac.new(
        api_secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

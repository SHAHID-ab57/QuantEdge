"""Base model and generic fallback for parsed WebSocket events."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WSEvent(BaseModel):
    """Base class for every parsed WebSocket event.

    ``received_at`` records when the event was parsed, in UTC. Extra
    payload fields are ignored.
    """

    model_config = ConfigDict(extra="ignore")

    type: str
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class UnknownWSEvent(WSEvent):
    """A well-formed frame whose ``type`` no registered model covers.

    Kept so newer or undocumented server messages never break the stream;
    the raw payload is preserved for inspection.
    """

    payload: dict[str, Any]

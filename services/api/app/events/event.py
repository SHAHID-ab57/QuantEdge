"""Base event model for the in-process event bus.

Every event carries five metadata fields — ``event_id``, ``event_type``,
``timestamp`` (UTC), ``source``, and ``payload`` — plus any typed fields
added by subclasses. The ``payload`` is the serializable "wire body" of
the event (all subclass fields); consumers may use the typed attributes
directly or the payload for storage/forwarding.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

_METADATA_FIELDS = frozenset(
    {"event_id", "event_type", "timestamp", "source", "payload"}
)


class Event(BaseModel):
    """Base class for every event published on the bus.

    Subclasses add typed domain fields. When ``event_type`` is omitted it
    defaults to the subclass name (e.g. ``MarketTradeReceived``).
    """

    model_config = ConfigDict(extra="ignore")

    event_id: UUID = Field(default_factory=uuid4)
    event_type: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: str
    payload: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        """Fill ``event_type`` from the class name and build the payload."""
        if not self.event_type:
            self.event_type = type(self).__name__
        if not self.payload:
            self.payload = {
                name: value
                for name, value in self.model_dump().items()
                if name not in _METADATA_FIELDS
            }
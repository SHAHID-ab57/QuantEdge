"""Parse raw WebSocket frames into typed events.

Malformed frames (invalid JSON, missing required fields, wrong field
types) are rejected: :meth:`MessageParser.parse` returns a
``ParsedMessage`` carrying the reason and never raises. Well-formed
frames with unregistered ``type`` values become ``UnknownWSEvent`` so
newer server messages cannot break the stream.
"""

import json
from dataclasses import dataclass

from pydantic import ValidationError

from app.ws.models import UnknownWSEvent, WSEvent


@dataclass(frozen=True)
class ParsedMessage:
    """Outcome of parsing one raw frame."""

    event: WSEvent | None = None
    error: str | None = None


class MessageParser:
    """Registry-driven parser keyed by the message ``type`` field.

    Register models with :meth:`register`. Patterns ending in ``*`` match
    any suffix (e.g. ``candlestick_*`` matches ``candlestick_1m``); exact
    types win over patterns.
    """

    def __init__(self) -> None:
        self._exact: dict[str, type[WSEvent]] = {}
        self._patterns: list[tuple[str, type[WSEvent]]] = []

    def register(self, message_type: str, model: type[WSEvent]) -> None:
        """Register ``model`` for frames with the given ``type``."""
        if message_type.endswith("*"):
            self._patterns.append((message_type[:-1], model))
        else:
            self._exact[message_type] = model

    def parse(self, raw: str) -> ParsedMessage:
        """Parse one raw frame into an event, or return the rejection reason."""
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            return ParsedMessage(error=f"invalid JSON: {exc.msg}")
        if not isinstance(payload, dict):
            return ParsedMessage(error="message is not a JSON object")
        message_type = payload.get("type")
        if not isinstance(message_type, str) or not message_type:
            return ParsedMessage(error="message has no string 'type' field")
        model = self._resolve(message_type)
        if model is None:
            return ParsedMessage(event=UnknownWSEvent(type=message_type, payload=payload))
        try:
            return ParsedMessage(event=model.model_validate(payload))
        except ValidationError as exc:
            return ParsedMessage(
                error=f"validation failed for {message_type}: {exc.errors(include_url=False)}"
            )

    def _resolve(self, message_type: str) -> type[WSEvent] | None:
        """Look up the registered model, falling back to patterns."""
        model = self._exact.get(message_type)
        if model is not None:
            return model
        for prefix, pattern_model in self._patterns:
            if message_type.startswith(prefix):
                return pattern_model
        return None

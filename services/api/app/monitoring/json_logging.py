"""One JSON object per log line.

A formatter change on the stdlib `logging` module, not a new logging
framework: every existing `logger.info(...)` call is untouched. Extra
fields passed as `logger.info("...", extra={"source": "fear_greed"})`
become top-level keys; an exception's traceback goes in `exception`. The
request context (`app.monitoring.context`) is added when a request is in
flight.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from app.monitoring.context import current_context

#: Attributes every `LogRecord` carries — everything else on a record was
#: put there by an `extra=` argument and is emitted as its own key.
_STANDARD_RECORD_ATTRS = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
) | {"message", "asctime", "taskName"}

#: Keys the formatter owns; an `extra=` key with the same name is dropped
#: rather than allowed to overwrite them.
_RESERVED_KEYS = frozenset({"timestamp", "level", "logger", "message", "exception"})


class JsonFormatter(logging.Formatter):
    """Format a `LogRecord` as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(current_context())
        for key, value in record.__dict__.items():
            if key in _STANDARD_RECORD_ATTRS or key in _RESERVED_KEYS or key.startswith("_"):
                continue
            payload.setdefault(key, value)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        elif record.exc_text:
            payload["exception"] = record.exc_text
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        # `default=str`: a log call passing a datetime/UUID/Decimal in
        # `extra` must never make the logging call itself raise.
        return json.dumps(payload, default=str, ensure_ascii=False)

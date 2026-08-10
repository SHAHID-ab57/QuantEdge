"""Shared ORM model foundation.

Provides the primary-key base class and timestamp mixin used by all
domain models. Timestamps are stored as timezone-aware UTC datetimes.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Uuid, func
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TimestampMixin:
    """Adds ``created_at`` and ``updated_at`` UTC timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class BaseModel(AsyncAttrs, Base):
    """Abstract base class providing the surrogate UUID primary key.

    ``AsyncAttrs`` enables ``await instance.attribute`` access for
    relationships in async contexts (see SQLAlchemy 2.x async docs).
    """

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    def __repr__(self) -> str:
        """Return a concise, debuggable representation of the instance."""
        attrs = ", ".join(f"{k}={v!r}" for k, v in self.__dict__.items() if not k.startswith("_"))
        return f"<{type(self).__name__}({attrs})>"

    def __eq__(self, other: Any) -> bool:
        """Compare models by identity when both sides carry ids.

        Falls back to the default identity comparison for unpersisted objects.
        """
        if isinstance(other, type(self)):
            return bool(self.id and other.id and self.id == other.id)
        return NotImplemented

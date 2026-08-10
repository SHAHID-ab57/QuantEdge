"""Exchange model — a trading venue whose market data is acquired."""

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, TimestampMixin

if TYPE_CHECKING:
    from app.models.market import Market


class Exchange(BaseModel, TimestampMixin):
    """A trading venue (e.g., Delta Exchange India, CoinGecko aggregator)."""

    __tablename__ = "exchanges"

    name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
    )
    slug: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        unique=True,
    )
    country: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="UTC",
        server_default="UTC",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    __table_args__ = (
        CheckConstraint(
            "length(name) > 0 AND length(slug) > 0",
            name="name_slug_nonempty",
        ),
    )

    markets: Mapped[list["Market"]] = relationship(
        back_populates="exchange",
        cascade="all, delete-orphan",
        lazy="raise",
    )

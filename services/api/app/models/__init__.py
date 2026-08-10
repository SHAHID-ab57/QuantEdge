"""ORM models package.

Importing this package registers every model on ``Base.metadata``; Alembic's
``env.py`` imports it to auto-discover tables for autogenerate.
"""

from app.models.base import BaseModel, TimestampMixin
from app.models.candle import Candle
from app.models.exchange import Exchange
from app.models.market import Market

__all__ = ["BaseModel", "TimestampMixin", "Candle", "Exchange", "Market"]

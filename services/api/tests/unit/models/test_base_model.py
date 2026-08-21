"""Unit tests for the shared ORM model foundation."""

import uuid

from app.models import Exchange, Market
from app.models.base import BaseModel


def test_timestamp_mixin_columns_exist() -> None:
    """Mapped models carry the UTC timestamp columns."""
    columns = Exchange.__table__.c
    assert "created_at" in columns
    assert "updated_at" in columns
    assert columns.created_at.nullable is False
    assert columns.updated_at.nullable is False


def test_base_model_repr_is_debuggable() -> None:
    """The repr shows the class name and non-private attributes."""
    exchange = Exchange(id=uuid.uuid4(), name="Delta Exchange", slug="delta")
    text = repr(exchange)
    assert text.startswith("<Exchange(")
    assert "name=" in text
    assert "Delta Exchange" in text
    assert "_sa_instance_state" not in text


def test_models_with_same_id_are_equal() -> None:
    """Equality compares by id when both sides are persisted."""
    exchange_id = uuid.uuid4()
    a = Exchange(id=exchange_id, name="Delta Exchange", slug="delta")
    b = Exchange(id=exchange_id, name="Delta Exchange", slug="delta")
    assert a == b
    assert b == a


def test_models_with_different_ids_are_unequal() -> None:
    """Different ids compare unequal even with identical fields."""
    a = Exchange(id=uuid.uuid4(), name="Delta Exchange", slug="delta")
    b = Exchange(id=uuid.uuid4(), name="Delta Exchange", slug="delta")
    assert a != b


def test_unpersisted_models_compare_false() -> None:
    """Without ids, equality returns False even against itself.

    ``__eq__`` is ``bool(self.id and other.id and ...)``, so unpersisted
    models (``id is None``) compare unequal by design; the docstring calls
    this the identity fallback, but the implemented semantics are "never
    equal without ids".
    """
    a = Exchange(name="Delta Exchange", slug="delta")
    b = Exchange(name="Delta Exchange", slug="delta")
    assert a is not b
    assert a != b
    assert a != a


def test_different_types_are_not_equal() -> None:
    """Equality returns NotImplemented across types."""
    exchange = Exchange(id=uuid.uuid4(), name="Delta Exchange", slug="delta")
    market = Market(id=uuid.uuid4(), symbol="ETHUSD")
    assert exchange != market
    assert market != exchange


def test_base_model_is_abstract_and_mixin_inherits() -> None:
    """The base classes are abstract foundations, not tables."""
    assert BaseModel.__abstract__ is True
    assert any(cls.__name__ == "TimestampMixin" for cls in Exchange.__mro__)
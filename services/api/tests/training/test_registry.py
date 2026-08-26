"""Tests for `ModelAdapterRegistry` and the builtin placeholder adapter's registration."""

import pytest

from app.training.adapters import load_builtin_model_adapters
from app.training.adapters.placeholder import PlaceholderModelAdapter
from app.training.base import ModelAdapter, ModelAdapterMetadata
from app.training.errors import DuplicateModelAdapterError, ModelAdapterNotFoundError
from app.training.registry import ModelAdapterRegistry, default_registry


class _FakeAdapter(ModelAdapter):
    metadata = ModelAdapterMetadata(
        name="fake", label="Fake", description="test double", framework="fake"
    )

    def initialize(self, hyperparameters):  # noqa: ANN001, ANN201 - test double
        return None

    def train(self, dataset, hyperparameters):  # noqa: ANN001, ANN201 - test double
        raise NotImplementedError


class TestRegister:
    def test_registers_and_resolves_by_name(self) -> None:
        registry = ModelAdapterRegistry()
        registry.register(_FakeAdapter)
        assert registry.has("fake") is True
        assert isinstance(registry.get("fake"), _FakeAdapter)

    def test_rejects_a_class_with_no_metadata(self) -> None:
        registry = ModelAdapterRegistry()

        class NoMetadata(ModelAdapter):
            def initialize(self, hyperparameters):  # noqa: ANN001, ANN201
                return None

            def train(self, dataset, hyperparameters):  # noqa: ANN001, ANN201
                raise NotImplementedError

        with pytest.raises(TypeError):
            registry.register(NoMetadata)

    def test_rejects_a_duplicate_name(self) -> None:
        registry = ModelAdapterRegistry()
        registry.register(_FakeAdapter)
        with pytest.raises(DuplicateModelAdapterError):
            registry.register(_FakeAdapter)


class TestGet:
    def test_raises_a_404_domain_error_for_an_unknown_name(self) -> None:
        registry = ModelAdapterRegistry()
        with pytest.raises(ModelAdapterNotFoundError) as exc_info:
            registry.get("does-not-exist")
        assert exc_info.value.status_code == 404
        assert exc_info.value.code == "model_adapter_not_found"


class TestDescribeAll:
    def test_returns_metadata_sorted_by_name(self) -> None:
        registry = ModelAdapterRegistry()

        class ZAdapter(ModelAdapter):
            metadata = ModelAdapterMetadata(name="zzz", label="Z", description="", framework="z")

            def initialize(self, hyperparameters):  # noqa: ANN001, ANN201
                return None

            def train(self, dataset, hyperparameters):  # noqa: ANN001, ANN201
                raise NotImplementedError

        registry.register(_FakeAdapter)
        registry.register(ZAdapter)
        names = [m.name for m in registry.describe_all()]
        assert names == ["fake", "zzz"]

    def test_len_and_iter(self) -> None:
        registry = ModelAdapterRegistry()
        registry.register(_FakeAdapter)
        assert len(registry) == 1
        assert [a.metadata.name for a in registry] == ["fake"]


class TestBuiltinPlaceholderAdapter:
    def test_load_builtin_model_adapters_registers_placeholder(self) -> None:
        load_builtin_model_adapters()
        assert default_registry.has("placeholder") is True
        assert isinstance(default_registry.get("placeholder"), PlaceholderModelAdapter)

    def test_is_idempotent(self) -> None:
        load_builtin_model_adapters()
        load_builtin_model_adapters()  # must not raise DuplicateModelAdapterError
        assert default_registry.has("placeholder") is True

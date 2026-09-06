"""Tests for the connector registry — mirrors
`tests/features/test_registry.py`'s own conventions (an isolated registry
per test, never the shared `default_registry`, so one test's registration
can't leak into another's).
"""

from typing import ClassVar

import pytest

from app.connectors.base import ConnectorMetadata, RawDataPoint
from app.connectors.errors import ConnectorNotFoundError, DuplicateConnectorError
from app.connectors.registry import ConnectorRegistry


class _FakeConnector:
    """A minimal, real (non-networking) `Connector` for registry tests."""

    #: Explicitly `ClassVar`-annotated, not just assigned: `Connector` is a
    #: structural `Protocol` declaring `metadata` as a `ClassVar`, and a
    #: type checker only accepts `type[_FakeConnector]` in place of
    #: `type[Connector]` (e.g. `registry.register(_FakeConnector)` below)
    #: once the concrete class's own attribute is annotated the same way
    #: — see `app.connectors.fear_greed.FearGreedConnector`'s own
    #: `metadata` for the real connector hitting this exact same rule.
    metadata: ClassVar[ConnectorMetadata] = ConnectorMetadata(
        source="fake_source",
        label="Fake Source",
        description="A connector used only to test the registry itself.",
    )

    def __init__(self) -> None:
        self.fetch_called = False

    async def fetch(self, start, end):  # noqa: ANN001, ANN201 - test double, matches Connector.fetch
        self.fetch_called = True
        return (RawDataPoint(timestamp=start, value=1.0),)


class TestRegisterAndGet:
    def test_register_then_get_builds_a_working_instance(self) -> None:
        registry = ConnectorRegistry()
        registry.register(_FakeConnector)

        connector = registry.get("fake_source")
        assert isinstance(connector, _FakeConnector)

    def test_get_builds_a_fresh_instance_every_call(self) -> None:
        """A connector is never a shared singleton — each `get()` call
        returns a brand-new instance, unlike `FeatureRegistry.get`."""
        registry = ConnectorRegistry()
        registry.register(_FakeConnector)

        first = registry.get("fake_source")
        second = registry.get("fake_source")
        assert first is not second

    def test_raises_for_an_unregistered_source(self) -> None:
        registry = ConnectorRegistry()
        with pytest.raises(ConnectorNotFoundError):
            registry.get("nope")

    def test_registering_a_class_with_no_metadata_raises_type_error(self) -> None:
        class NoMetadata:
            async def fetch(self, start, end):  # noqa: ANN001, ANN201
                return ()

        registry = ConnectorRegistry()
        with pytest.raises(TypeError):
            registry.register(NoMetadata)  # type: ignore[arg-type]

    def test_registering_the_same_source_twice_raises(self) -> None:
        registry = ConnectorRegistry()
        registry.register(_FakeConnector)
        with pytest.raises(DuplicateConnectorError):
            registry.register(_FakeConnector)


class TestDescribe:
    def test_describe_returns_metadata_without_instantiating(self) -> None:
        registry = ConnectorRegistry()
        registry.register(_FakeConnector)

        metadata = registry.describe("fake_source")
        assert metadata.source == "fake_source"
        assert metadata.label == "Fake Source"

    def test_describe_raises_for_an_unregistered_source(self) -> None:
        registry = ConnectorRegistry()
        with pytest.raises(ConnectorNotFoundError):
            registry.describe("nope")

    def test_describe_all_lists_every_registered_connector_sorted(self) -> None:
        class AnotherConnector:
            metadata: ClassVar[ConnectorMetadata] = ConnectorMetadata(
                source="another_source", label="Another", description="Another test connector."
            )

            async def fetch(self, start, end):  # noqa: ANN001, ANN201
                return ()

        registry = ConnectorRegistry()
        registry.register(AnotherConnector)
        registry.register(_FakeConnector)

        assert [entry.source for entry in registry.describe_all()] == [
            "another_source",
            "fake_source",
        ]


class TestNamesHasLen:
    def test_has_and_names_and_len(self) -> None:
        registry = ConnectorRegistry()
        assert not registry.has("fake_source")
        assert registry.names() == ()
        assert len(registry) == 0

        registry.register(_FakeConnector)
        assert registry.has("fake_source")
        assert registry.names() == ("fake_source",)
        assert len(registry) == 1
        assert list(registry) == ["fake_source"]


class TestFearGreedIsRegistered:
    """The real, application-wide registry — proves the new connector is
    genuinely discoverable, not just the isolated-registry mechanics
    above."""

    def test_the_default_registry_lists_fear_greed_after_loading_builtins(self) -> None:
        from app.connectors import load_builtin_connectors
        from app.connectors.fear_greed import FEAR_GREED_SOURCE
        from app.connectors.registry import default_registry

        load_builtin_connectors()

        assert FEAR_GREED_SOURCE in default_registry.names()
        metadata = default_registry.describe(FEAR_GREED_SOURCE)
        assert metadata.label == "Fear & Greed Index"
        assert metadata.requires_auth is False
        assert metadata.frequency == "daily"

    async def test_get_builds_a_real_fear_greed_connector(self) -> None:
        from app.connectors import load_builtin_connectors
        from app.connectors.fear_greed import FEAR_GREED_SOURCE, FearGreedConnector
        from app.connectors.registry import default_registry

        load_builtin_connectors()
        connector = default_registry.get(FEAR_GREED_SOURCE)
        # Asserted before `aclose()`, deliberately: `get()`'s own declared
        # return type is the `Connector` protocol, which doesn't include
        # `aclose()` — a type checker only accepts the call below once
        # `connector` has been narrowed to the concrete class this way.
        assert isinstance(connector, FearGreedConnector)
        await connector.aclose()


class TestFredIsRegistered:
    """The real, application-wide registry — proves the FRED connector is
    genuinely discoverable, not just the isolated-registry mechanics
    above."""

    def test_the_default_registry_lists_fred_after_loading_builtins(self) -> None:
        from app.connectors import load_builtin_connectors
        from app.connectors.fred import FRED_SOURCE
        from app.connectors.registry import default_registry

        load_builtin_connectors()

        assert FRED_SOURCE in default_registry.names()
        metadata = default_registry.describe(FRED_SOURCE)
        assert metadata.label == "Federal Funds Rate"
        assert metadata.requires_auth is True
        assert metadata.frequency == "monthly"

    async def test_get_builds_a_real_fred_connector(self) -> None:
        from app.connectors import load_builtin_connectors
        from app.connectors.fred import FRED_SOURCE, FredConnector
        from app.connectors.registry import default_registry

        load_builtin_connectors()
        connector = default_registry.get(FRED_SOURCE)
        assert isinstance(connector, FredConnector)
        await connector.aclose()


class TestEtherscanIsRegistered:
    """The real, application-wide registry — proves the Etherscan
    connector is genuinely discoverable, not just the isolated-registry
    mechanics above."""

    def test_the_default_registry_lists_etherscan_after_loading_builtins(self) -> None:
        from app.connectors import load_builtin_connectors
        from app.connectors.etherscan import ETHERSCAN_SOURCE
        from app.connectors.registry import default_registry

        load_builtin_connectors()

        assert ETHERSCAN_SOURCE in default_registry.names()
        metadata = default_registry.describe(ETHERSCAN_SOURCE)
        assert metadata.label == "Ethereum Gas Price"
        assert metadata.requires_auth is True

    async def test_get_builds_a_real_etherscan_connector(self) -> None:
        from app.connectors import load_builtin_connectors
        from app.connectors.etherscan import ETHERSCAN_SOURCE, EtherscanConnector
        from app.connectors.registry import default_registry

        load_builtin_connectors()
        connector = default_registry.get(ETHERSCAN_SOURCE)
        assert isinstance(connector, EtherscanConnector)
        await connector.aclose()


class TestDefiLlamaIsRegistered:
    """The real, application-wide registry — proves the DefiLlama
    connector is genuinely discoverable, not just the isolated-registry
    mechanics above."""

    def test_the_default_registry_lists_defillama_after_loading_builtins(self) -> None:
        from app.connectors import load_builtin_connectors
        from app.connectors.defillama import DEFILLAMA_SOURCE
        from app.connectors.registry import default_registry

        load_builtin_connectors()

        assert DEFILLAMA_SOURCE in default_registry.names()
        metadata = default_registry.describe(DEFILLAMA_SOURCE)
        assert metadata.label == "Ethereum Chain TVL"
        assert metadata.requires_auth is False
        assert metadata.revisable is True

    async def test_get_builds_a_real_defillama_connector(self) -> None:
        from app.connectors import load_builtin_connectors
        from app.connectors.defillama import DEFILLAMA_SOURCE, DefiLlamaConnector
        from app.connectors.registry import default_registry

        load_builtin_connectors()
        connector = default_registry.get(DEFILLAMA_SOURCE)
        assert isinstance(connector, DefiLlamaConnector)
        await connector.aclose()

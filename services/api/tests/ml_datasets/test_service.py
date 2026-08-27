"""MLDatasetService tests — the join between stored candles and the ML Dataset Builder.

Exercises the service against the in-memory SQLite database the rest of
the suite uses, so the ORM → `OHLCVPoint` projection and the shared
market/timeframe/range validation are covered against real rows, mirroring
`tests/features/test_service.py`'s exact convention.
"""

import uuid

import pytest

from app.dataset_validation.engine import DatasetValidator
from app.dataset_validation.registry import default_registry as rule_registry
from app.dataset_validation.rules import load_builtin_rules
from app.features.builtin import load_builtin_features
from app.features.dataset import FeatureDatasetBuilder
from app.features.pipeline import FeaturePipeline
from app.features.registry import default_registry as feature_registry
from app.ml_datasets.dataset import MLDatasetBuilder
from app.ml_datasets.errors import (
    InvalidMLDatasetBuildSortError,
    MLDatasetBuildNotFoundError,
    TargetNotFoundError,
)
from app.ml_datasets.pipeline import TargetPipeline
from app.ml_datasets.registry import default_registry as target_registry
from app.ml_datasets.split import ChronologicalSplitter
from app.ml_datasets.targets import load_builtin_targets
from app.repositories.candles import CandleRepository
from app.repositories.markets import MarketRepository
from app.repositories.ml_dataset_builds import MLDatasetBuildRepository
from app.schemas.features import FeatureRequestItem
from app.schemas.ml_datasets import MLDatasetRequest, MLTargetRequestItem
from app.services.ml_datasets import MLDatasetService, _cap_rows
from tests.conftest import SessionFactory
from tests.ml_datasets.conftest import candles as synthetic_candles


def build_service(session_factory: SessionFactory) -> MLDatasetService:
    """An MLDatasetService over the test database and the real registries."""
    load_builtin_features()
    load_builtin_rules()
    load_builtin_targets()
    session = session_factory()
    return MLDatasetService(
        candle_repository=CandleRepository(session),
        market_repository=MarketRepository(session),
        builder=MLDatasetBuilder(
            feature_builder=FeatureDatasetBuilder(FeaturePipeline(feature_registry)),
            target_pipeline=TargetPipeline(target_registry),
            validator=DatasetValidator(rule_registry),
            splitter=ChronologicalSplitter(),
        ),
        default_limit=100,
        max_limit=1000,
        build_repository=MLDatasetBuildRepository(session),
    )


def request(**kwargs: object) -> MLDatasetRequest:
    """A default ML dataset request over 1h candles, overridable per test."""
    payload: dict[str, object] = {
        "timeframe": "1h",
        "features": [FeatureRequestItem(feature="ohlcv")],
        "targets": [MLTargetRequestItem(target="next_close")],
    }
    payload.update(kwargs)
    return MLDatasetRequest(**payload)  # type: ignore[arg-type]


class TestCatalogue:
    def test_lists_every_registered_target(self, session_factory: SessionFactory) -> None:
        catalogue = build_service(session_factory).list_targets()
        names = {entry.name for entry in catalogue.targets}
        assert {"next_close", "next_direction", "next_return"} <= names
        assert catalogue.total == len(catalogue.targets)

    def test_describes_a_single_target(self, session_factory: SessionFactory) -> None:
        target = build_service(session_factory).get_target("next_close")
        assert target.category == "price"

    def test_raises_for_an_unknown_target(self, session_factory: SessionFactory) -> None:
        with pytest.raises(TargetNotFoundError):
            build_service(session_factory).get_target("nope")


class TestBuildDataset:
    async def test_builds_over_stored_candles(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        response = await build_service(session_factory).build_dataset("ETCUSD", request())
        assert response.symbol == "ETCUSD"
        assert "next_close_1" in response.target_columns
        assert response.meta.row_count == len(response.rows)

    async def test_reports_the_split_verdict_and_bounds(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        response = await build_service(session_factory).build_dataset("ETCUSD", request())
        total = (
            response.split_bounds.train_rows
            + response.split_bounds.validation_rows
            + response.split_bounds.test_rows
        )
        assert total == response.meta.row_count
        assert isinstance(response.validation.passed, bool)

    async def test_every_row_carries_a_split_label(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        response = await build_service(session_factory).build_dataset("ETCUSD", request())
        assert len(response.split) == len(response.rows)
        assert all(label in ("train", "validation", "test") for label in response.split)

    async def test_limit_caps_rows_and_re_splits(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        # seeded_varied has 3 candles; next_close(horizon=1) leaves 2 rows.
        # Capping to 1 must re-derive the split over exactly that 1 row.
        response = await build_service(session_factory).build_dataset("ETCUSD", request(limit=1))
        assert response.meta.row_count == 1
        assert len(response.rows) == 1
        assert len(response.split) == 1
        assert (
            response.split_bounds.train_rows
            + response.split_bounds.validation_rows
            + response.split_bounds.test_rows
            == 1
        )

    async def test_preview_rows_truncates_the_response_but_not_dataset_history(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        # seeded_varied leaves 2 rows after horizon trimming (see the test above).
        service = build_service(session_factory)

        response = await service.build_dataset("ETCUSD", request(preview_rows=1))

        assert len(response.rows) == 1
        assert response.meta.truncated is True

        listing = await service.list_builds(
            symbol=None,
            timeframe=None,
            quality_passed=None,
            sort="created_at",
            direction="desc",
            limit=20,
            offset=0,
        )
        detail = await service.get_build(uuid.UUID(listing.builds[0].id))
        assert len(detail.dataset.rows) == 2


class TestCapRows:
    """Direct unit coverage of `_cap_rows`'s actual-trim branch.

    The service-level "limit caps rows" behavior is proven end to end in
    `TestBuildDataset.test_limit_caps_rows_and_re_splits` above; that test
    can't force the assembled (pre-cap) matrix to exceed the requested
    limit without also controlling `max_limit`, so this test calls
    `_cap_rows` directly with a dataset already larger than the limit —
    the one case a real request can produce it (a resolved limit whose
    widened candle window would exceed the server's configured maximum).
    """

    def test_trims_to_the_limit_and_re_splits(self) -> None:
        from app.dataset_validation.engine import DatasetValidator
        from app.dataset_validation.registry import default_registry as rule_registry
        from app.dataset_validation.rules import load_builtin_rules
        from app.features.builtin import load_builtin_features
        from app.features.dataset import FeatureDatasetBuilder, FeatureRequest
        from app.features.pipeline import FeaturePipeline
        from app.features.registry import default_registry as feature_registry
        from app.ml_datasets.dataset import MLDatasetBuilder, TargetRequest
        from app.ml_datasets.pipeline import TargetPipeline
        from app.ml_datasets.registry import default_registry as target_registry
        from app.ml_datasets.split import ChronologicalSplitter
        from app.ml_datasets.targets import load_builtin_targets

        load_builtin_features()
        load_builtin_rules()
        load_builtin_targets()
        builder = MLDatasetBuilder(
            feature_builder=FeatureDatasetBuilder(FeaturePipeline(feature_registry)),
            target_pipeline=TargetPipeline(target_registry),
            validator=DatasetValidator(rule_registry),
            splitter=ChronologicalSplitter(),
        )
        ml_dataset = builder.build(
            "ETHUSD",
            "1h",
            synthetic_candles(10),
            [FeatureRequest("ohlcv")],
            [TargetRequest("next_close")],
        )
        assert ml_dataset.dataset.row_count == 9  # 10 candles - 1 horizon row

        capped = _cap_rows(ml_dataset, 3)
        assert capped.dataset.row_count == 3
        assert capped.dataset.quality.rows_returned == 3
        assert (
            capped.split.train.row_count
            + capped.split.validation.row_count
            + capped.split.test.row_count
            == 3
        )

    def test_is_a_no_op_when_already_within_the_limit(self) -> None:
        from app.dataset_validation.engine import DatasetValidator
        from app.dataset_validation.registry import default_registry as rule_registry
        from app.dataset_validation.rules import load_builtin_rules
        from app.features.builtin import load_builtin_features
        from app.features.dataset import FeatureDatasetBuilder, FeatureRequest
        from app.features.pipeline import FeaturePipeline
        from app.features.registry import default_registry as feature_registry
        from app.ml_datasets.dataset import MLDatasetBuilder, TargetRequest
        from app.ml_datasets.pipeline import TargetPipeline
        from app.ml_datasets.registry import default_registry as target_registry
        from app.ml_datasets.split import ChronologicalSplitter
        from app.ml_datasets.targets import load_builtin_targets

        load_builtin_features()
        load_builtin_rules()
        load_builtin_targets()
        builder = MLDatasetBuilder(
            feature_builder=FeatureDatasetBuilder(FeaturePipeline(feature_registry)),
            target_pipeline=TargetPipeline(target_registry),
            validator=DatasetValidator(rule_registry),
            splitter=ChronologicalSplitter(),
        )
        ml_dataset = builder.build(
            "ETHUSD",
            "1h",
            synthetic_candles(5),
            [FeatureRequest("ohlcv")],
            [TargetRequest("next_close")],
        )
        assert _cap_rows(ml_dataset, 100) is ml_dataset


class TestExportDataset:
    async def test_exports_a_csv_download(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        exported = await build_service(session_factory).export_dataset("ETCUSD", request(), "csv")
        assert exported.media_type.startswith("text/csv")
        assert "next_close_1" in exported.content

    async def test_exports_a_json_download(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        exported = await build_service(session_factory).export_dataset("ETCUSD", request(), "json")
        assert exported.media_type.startswith("application/json")
        assert "ml_dataset_id" in exported.content


class TestDatasetHistory:
    """`build_dataset` persists to Dataset History; `build_ml_dataset`/`export_dataset`
    (the Training Framework's and the Export dialog's own reuse of this service) must
    not — only an explicit `/ml-datasets` build should grow that history."""

    async def test_build_dataset_persists_a_history_entry(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        service = build_service(session_factory)

        await service.build_dataset("ETCUSD", request())

        listing = await service.list_builds(
            symbol=None,
            timeframe=None,
            quality_passed=None,
            sort="created_at",
            direction="desc",
            limit=20,
            offset=0,
        )
        assert listing.total == 1
        assert listing.builds[0].symbol == "ETCUSD"
        assert listing.builds[0].row_count > 0

    async def test_build_ml_dataset_does_not_add_to_history(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        service = build_service(session_factory)

        await service.build_ml_dataset("ETCUSD", request())

        listing = await service.list_builds(
            symbol=None,
            timeframe=None,
            quality_passed=None,
            sort="created_at",
            direction="desc",
            limit=20,
            offset=0,
        )
        assert listing.total == 0

    async def test_export_dataset_does_not_add_to_history(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        service = build_service(session_factory)

        await service.export_dataset("ETCUSD", request(), "csv")

        listing = await service.list_builds(
            symbol=None,
            timeframe=None,
            quality_passed=None,
            sort="created_at",
            direction="desc",
            limit=20,
            offset=0,
        )
        assert listing.total == 0

    async def test_get_build_returns_the_full_stored_dataset_rows_included(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        service = build_service(session_factory)
        built = await service.build_dataset("ETCUSD", request())
        listing = await service.list_builds(
            symbol=None,
            timeframe=None,
            quality_passed=None,
            sort="created_at",
            direction="desc",
            limit=20,
            offset=0,
        )
        build_id = listing.builds[0].id

        detail = await service.get_build(uuid.UUID(build_id))

        assert detail.dataset.rows == built.rows
        assert detail.dataset.ml_dataset_id == built.ml_dataset_id

    async def test_get_build_raises_not_found_for_an_unknown_id(
        self, session_factory: SessionFactory
    ) -> None:
        with pytest.raises(MLDatasetBuildNotFoundError):
            await build_service(session_factory).get_build(uuid.uuid4())

    async def test_deletes_a_build(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        service = build_service(session_factory)
        await service.build_dataset("ETCUSD", request())
        listing = await service.list_builds(
            symbol=None,
            timeframe=None,
            quality_passed=None,
            sort="created_at",
            direction="desc",
            limit=20,
            offset=0,
        )
        build_id = uuid.UUID(listing.builds[0].id)

        await service.delete_build(build_id)

        with pytest.raises(MLDatasetBuildNotFoundError):
            await service.get_build(build_id)

    async def test_delete_raises_not_found_for_an_unknown_id(
        self, session_factory: SessionFactory
    ) -> None:
        with pytest.raises(MLDatasetBuildNotFoundError):
            await build_service(session_factory).delete_build(uuid.uuid4())

    async def test_filters_by_timeframe(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        service = build_service(session_factory)
        await service.build_dataset("ETCUSD", request())

        matching = await service.list_builds(
            symbol=None,
            timeframe="1h",
            quality_passed=None,
            sort="created_at",
            direction="desc",
            limit=20,
            offset=0,
        )
        not_matching = await service.list_builds(
            symbol=None,
            timeframe="1d",
            quality_passed=None,
            sort="created_at",
            direction="desc",
            limit=20,
            offset=0,
        )
        assert matching.total == 1
        assert not_matching.total == 0

    async def test_filters_by_quality_passed(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        service = build_service(session_factory)
        await service.build_dataset("ETCUSD", request())

        passed = await service.list_builds(
            symbol=None,
            timeframe=None,
            quality_passed=True,
            sort="created_at",
            direction="desc",
            limit=20,
            offset=0,
        )
        failed = await service.list_builds(
            symbol=None,
            timeframe=None,
            quality_passed=False,
            sort="created_at",
            direction="desc",
            limit=20,
            offset=0,
        )
        assert passed.total == 1
        assert failed.total == 0

    async def test_a_failed_persist_does_not_fail_the_build_itself(
        self, session_factory: SessionFactory, seeded_varied: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`_record_build` is best-effort — a researcher must still get their dataset
        back even if Dataset History fails to persist it."""
        service = build_service(session_factory)

        async def broken_create(*args: object, **kwargs: object) -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr(service.build_repository, "create", broken_create)

        response = await service.build_dataset("ETCUSD", request())

        assert response.symbol == "ETCUSD"

    async def test_filters_by_symbol(
        self, session_factory: SessionFactory, seeded_varied: None
    ) -> None:
        service = build_service(session_factory)
        await service.build_dataset("ETCUSD", request())

        listing = await service.list_builds(
            symbol="DOES-NOT-EXIST",
            timeframe=None,
            quality_passed=None,
            sort="created_at",
            direction="desc",
            limit=20,
            offset=0,
        )
        assert listing.total == 0

    async def test_search_rejects_an_invalid_sort_column(
        self, session_factory: SessionFactory
    ) -> None:
        with pytest.raises(InvalidMLDatasetBuildSortError):
            await build_service(session_factory).list_builds(
                symbol=None,
                timeframe=None,
                quality_passed=None,
                sort="not_a_column",
                direction="asc",
                limit=20,
                offset=0,
            )

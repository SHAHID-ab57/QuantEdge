"""ML dataset export tests — CSV/JSON round-trip fidelity, provenance, and the split column."""

import csv
import io
import json

import pytest

from app.dataset_validation.engine import DatasetValidator
from app.dataset_validation.registry import default_registry as rule_registry
from app.dataset_validation.rules import load_builtin_rules
from app.features.ai_extensions import SplitRatios
from app.features.builtin import load_builtin_features
from app.features.dataset import FeatureDatasetBuilder, FeatureRequest
from app.features.pipeline import FeaturePipeline
from app.features.registry import default_registry as feature_registry
from app.ml_datasets.dataset import MLDatasetBuilder, TargetRequest
from app.ml_datasets.export import EXPORT_FORMATS, dataset_filename, to_csv, to_json
from app.ml_datasets.pipeline import TargetPipeline
from app.ml_datasets.registry import default_registry as target_registry
from app.ml_datasets.split import ChronologicalSplitter
from app.ml_datasets.targets import load_builtin_targets
from tests.ml_datasets.conftest import candles


@pytest.fixture(scope="module")
def builder() -> MLDatasetBuilder:
    load_builtin_features()
    load_builtin_rules()
    load_builtin_targets()
    return MLDatasetBuilder(
        feature_builder=FeatureDatasetBuilder(FeaturePipeline(feature_registry)),
        target_pipeline=TargetPipeline(target_registry),
        validator=DatasetValidator(rule_registry),
        splitter=ChronologicalSplitter(),
    )


@pytest.fixture
def ml_dataset(builder: MLDatasetBuilder):
    return builder.build(
        "ETHUSD",
        "1h",
        candles(20),
        [FeatureRequest("ohlcv")],
        [TargetRequest("next_close")],
        split_ratios=SplitRatios(train=0.6, validation=0.2, test=0.2),
    )


class TestCsvExport:
    def test_header_names_every_column_plus_split(self, ml_dataset) -> None:
        text = to_csv(ml_dataset)
        rows = list(csv.reader(io.StringIO(text)))
        header = next(row for row in rows if row and row[0] == "timestamp")
        assert header == [
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "next_close_1",
            "split",
        ]

    def test_every_data_row_carries_a_split_label(self, ml_dataset) -> None:
        text = to_csv(ml_dataset)
        rows = list(csv.reader(io.StringIO(text)))
        data_rows = [
            row for row in rows if row and not row[0].startswith("#") and row[0] != "timestamp"
        ]
        assert len(data_rows) == ml_dataset.dataset.row_count
        assert all(row[-1] in ("train", "validation", "test") for row in data_rows)

    def test_split_labels_respect_the_configured_ratios(self, ml_dataset) -> None:
        text = to_csv(ml_dataset)
        rows = list(csv.reader(io.StringIO(text)))
        data_rows = [
            row for row in rows if row and not row[0].startswith("#") and row[0] != "timestamp"
        ]
        labels = [row[-1] for row in data_rows]
        assert labels.count("train") == ml_dataset.split.train.row_count
        assert labels.count("validation") == ml_dataset.split.validation.row_count
        assert labels.count("test") == ml_dataset.split.test.row_count

    def test_metadata_preamble_names_the_dataset_and_targets(self, ml_dataset) -> None:
        text = to_csv(ml_dataset)
        assert f"ml_dataset_id,{ml_dataset.ml_dataset_id}" in text
        assert "target.next_close,version=1.0.0 horizon=1 columns=(next_close_1)" in text

    def test_metadata_can_be_omitted(self, ml_dataset) -> None:
        text = to_csv(ml_dataset, include_metadata=False)
        assert "#" not in text

    def test_generation_failures_are_listed_in_the_preamble(
        self, builder: MLDatasetBuilder
    ) -> None:
        ml = builder.build(
            "ETHUSD",
            "1h",
            candles(10),
            [FeatureRequest("ohlcv")],
            [TargetRequest("does_not_exist"), TargetRequest("next_close")],
        )
        text = to_csv(ml)
        assert "quality.generation_failure,does_not_exist:" in text

    def test_null_cells_render_empty(self, builder: MLDatasetBuilder) -> None:
        ml = builder.build(
            "ETHUSD",
            "1h",
            candles(10),
            [FeatureRequest("ohlcv")],
            [TargetRequest("next_close")],
            drop_undefined_targets=False,
        )
        rows = list(csv.reader(io.StringIO(to_csv(ml))))
        data_rows = [
            row for row in rows if row and not row[0].startswith("#") and row[0] != "timestamp"
        ]
        # The target column sits second-to-last (before `split`); the very
        # last candle has no future close, so its target cell is empty.
        assert data_rows[-1][-2] == ""
        assert data_rows[-1][-1] == "test"


class TestJsonExport:
    def test_top_level_fields_present(self, ml_dataset) -> None:
        payload = json.loads(to_json(ml_dataset))
        assert payload["ml_dataset_id"] == ml_dataset.ml_dataset_id
        assert payload["dataset_id"] == ml_dataset.dataset.dataset_id
        assert payload["feature_columns"] == list(ml_dataset.feature_columns)
        assert payload["target_columns"] == list(ml_dataset.target_columns)

    def test_split_bounds_match_the_actual_split(self, ml_dataset) -> None:
        payload = json.loads(to_json(ml_dataset))
        assert payload["split_bounds"]["train_rows"] == ml_dataset.split.train.row_count
        assert payload["split_bounds"]["validation_rows"] == ml_dataset.split.validation.row_count
        assert payload["split_bounds"]["test_rows"] == ml_dataset.split.test.row_count

    def test_every_row_carries_its_split_label(self, ml_dataset) -> None:
        payload = json.loads(to_json(ml_dataset))
        assert len(payload["data"]) == ml_dataset.dataset.row_count
        assert all(row["split"] in ("train", "validation", "test") for row in payload["data"])

    def test_validation_verdict_is_embedded(self, ml_dataset) -> None:
        payload = json.loads(to_json(ml_dataset))
        assert payload["validation"]["passed"] == ml_dataset.validation.passed
        assert payload["validation"]["summary"]["errors"] == ml_dataset.validation.summary.errors

    def test_targets_list_their_own_provenance(self, ml_dataset) -> None:
        payload = json.loads(to_json(ml_dataset))
        assert payload["targets"][0]["target"] == "next_close"
        assert payload["targets"][0]["horizon"] == 1


class TestFilenameAndFormats:
    def test_filename_is_stable_and_safe(self, ml_dataset) -> None:
        name = dataset_filename(ml_dataset, "csv")
        assert name.endswith(".csv")
        assert "ETHUSD" in name
        assert "/" not in name

    def test_registers_csv_and_json(self) -> None:
        assert set(EXPORT_FORMATS) == {"csv", "json"}
        assert EXPORT_FORMATS["csv"].binary is False
        assert EXPORT_FORMATS["json"].binary is False

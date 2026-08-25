"""Dataset export tests — CSV and JSON serialization.

Both formats must round-trip the matrix faithfully *and* carry enough
provenance to reproduce it. An exported file that cannot say which pipeline
and feature versions produced it is not research output.
"""

import csv
import io
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.features.base import OHLCVPoint
from app.features.builtin import load_builtin_features
from app.features.dataset import FeatureDataset, FeatureDatasetBuilder, FeatureRequest
from app.features.export import dataset_filename, to_csv, to_json
from app.features.pipeline import FeaturePipeline
from app.features.registry import default_registry


@pytest.fixture(scope="module")
def builder() -> FeatureDatasetBuilder:
    load_builtin_features()
    return FeatureDatasetBuilder(FeaturePipeline(default_registry))


def candles(count: int) -> list[OHLCVPoint]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        OHLCVPoint(
            open_time=base + timedelta(hours=i),
            open=100.0 + i,
            high=105.0 + i,
            low=95.0 + i,
            close=102.0 + i,
            volume=10.0 + i,
        )
        for i in range(count)
    ]


@pytest.fixture
def dataset(builder: FeatureDatasetBuilder) -> FeatureDataset:
    """A small mixed-dtype dataset: floats, a categorical, and a moving average."""
    return builder.build(
        "ETHUSD",
        "1h",
        candles(6),
        [
            FeatureRequest("ohlcv"),
            FeatureRequest("candle_shape"),
            FeatureRequest("sma", {"period": "2"}),
        ],
    )


def parse_matrix(content: str) -> tuple[list[str], list[list[str]]]:
    """Read a CSV export back the way pandas would: skipping ``#`` comments."""
    lines = [line for line in content.splitlines() if not line.startswith("#")]
    rows = list(csv.reader(io.StringIO("\n".join(lines))))
    return rows[0], rows[1:]


class TestCsv:
    def test_writes_a_header_of_timestamp_plus_every_column(self, dataset: FeatureDataset) -> None:
        header, _ = parse_matrix(to_csv(dataset))
        assert header[0] == "timestamp"
        assert header[1:] == [column.name for column in dataset.columns]

    def test_writes_one_row_per_dataset_row(self, dataset: FeatureDataset) -> None:
        _, rows = parse_matrix(to_csv(dataset))
        assert len(rows) == dataset.row_count

    def test_every_row_has_one_cell_per_header_column(self, dataset: FeatureDataset) -> None:
        header, rows = parse_matrix(to_csv(dataset))
        for row in rows:
            assert len(row) == len(header)

    def test_timestamps_are_iso_utc_with_a_literal_z(self, dataset: FeatureDataset) -> None:
        _, rows = parse_matrix(to_csv(dataset))
        assert rows[0][0].endswith("Z")
        assert datetime.fromisoformat(rows[0][0].replace("Z", "+00:00")).tzinfo is not None

    def test_preserves_a_categorical_value_as_text(self, dataset: FeatureDataset) -> None:
        header, rows = parse_matrix(to_csv(dataset))
        direction = header.index("candle_direction")
        assert rows[0][direction] in {"up", "down", "flat"}

    def test_writes_a_null_as_an_empty_field(self, builder: FeatureDatasetBuilder) -> None:
        # Empty is the CSV convention for "no value" and is what pandas
        # reads back as NaN; the string "None" would poison the column dtype.
        untrimmed = builder.build(
            "ETHUSD",
            "1h",
            candles(4),
            [FeatureRequest("sma", {"period": "2"})],
            drop_warmup=False,
        )
        _, rows = parse_matrix(to_csv(untrimmed))
        assert rows[0][1] == ""

    def test_metadata_preamble_is_comment_prefixed_so_naive_parsers_still_work(
        self, dataset: FeatureDataset
    ) -> None:
        content = to_csv(dataset)
        preamble = [line for line in content.splitlines() if line.startswith("#")]
        assert preamble
        assert all(line.startswith("# ") for line in preamble)

    def test_metadata_records_provenance(self, dataset: FeatureDataset) -> None:
        content = to_csv(dataset)
        assert "# symbol,ETHUSD" in content
        assert "# timeframe,1h" in content
        assert "# pipeline_version," in content
        assert "# rows_dropped," in content
        assert "# warmup_candles," in content

    def test_metadata_names_every_feature_with_its_parameters_and_version(
        self, dataset: FeatureDataset
    ) -> None:
        content = to_csv(dataset)
        sma_line = next(line for line in content.splitlines() if line.startswith("# feature.sma,"))
        assert "version=1.0.0" in sma_line
        assert "period=2" in sma_line
        assert "source=close" in sma_line
        assert "columns=(sma_2)" in sma_line
        ohlcv_line = next(
            line for line in content.splitlines() if line.startswith("# feature.ohlcv,")
        )
        assert "version=1.0.0" in ohlcv_line

    def test_metadata_includes_the_dataset_id_and_export_timestamp(
        self, dataset: FeatureDataset
    ) -> None:
        content = to_csv(dataset)
        assert f"# dataset_id,{dataset.dataset_id}" in content
        exported_line = next(
            line for line in content.splitlines() if line.startswith("# exported_at,")
        )
        assert exported_line.endswith("Z")

    def test_metadata_includes_the_quality_summary(self, dataset: FeatureDataset) -> None:
        content = to_csv(dataset)
        assert "# quality.duplicate_timestamps,0" in content
        assert "# quality.missing_candles," in content
        assert "# quality.generation_time_ms," in content

    def test_metadata_can_be_omitted_for_a_bare_matrix(self, dataset: FeatureDataset) -> None:
        content = to_csv(dataset, include_metadata=False)
        assert not content.startswith("#")
        assert content.splitlines()[0].startswith("timestamp,")

    def test_an_empty_dataset_still_writes_a_usable_header(
        self, builder: FeatureDatasetBuilder
    ) -> None:
        empty = builder.build("ETHUSD", "1h", candles(3), [])
        header, rows = parse_matrix(to_csv(empty))
        assert header == ["timestamp"]
        assert rows == []


class TestJson:
    def test_emits_one_record_per_row_by_default(self, dataset: FeatureDataset) -> None:
        payload = json.loads(to_json(dataset))
        assert len(payload["data"]) == dataset.row_count
        assert isinstance(payload["data"][0], dict)

    def test_records_are_keyed_by_column_name(self, dataset: FeatureDataset) -> None:
        payload = json.loads(to_json(dataset))
        record = payload["data"][0]
        assert "timestamp" in record
        for column in dataset.columns:
            assert column.name in record

    def test_column_orientation_emits_parallel_arrays(self, dataset: FeatureDataset) -> None:
        payload = json.loads(to_json(dataset, orient="columns"))
        assert isinstance(payload["data"], dict)
        assert len(payload["timestamps"]) == dataset.row_count
        for column in dataset.columns:
            assert len(payload["data"][column.name]) == dataset.row_count

    def test_both_orientations_carry_the_same_values(self, dataset: FeatureDataset) -> None:
        records = json.loads(to_json(dataset, orient="records"))["data"]
        columns = json.loads(to_json(dataset, orient="columns"))["data"]
        first_column = dataset.columns[0].name
        assert [record[first_column] for record in records] == columns[first_column]

    def test_describes_every_column_with_its_dtype(self, dataset: FeatureDataset) -> None:
        payload = json.loads(to_json(dataset))
        by_name = {column["name"]: column for column in payload["columns"]}
        assert by_name["candle_direction"]["dtype"] == "categorical"
        assert by_name["close"]["dtype"] == "float"

    def test_records_feature_provenance(self, dataset: FeatureDataset) -> None:
        payload = json.loads(to_json(dataset))
        sma = next(entry for entry in payload["features"] if entry["feature"] == "sma")
        assert sma["params"] == {"period": 2, "source": "close"}
        assert sma["version"] == "1.0.0"
        assert sma["columns"] == ["sma_2"]

    def test_records_dataset_meta(self, dataset: FeatureDataset) -> None:
        payload = json.loads(to_json(dataset))
        assert payload["meta"]["row_count"] == dataset.row_count
        assert payload["meta"]["candles_analyzed"] == dataset.candles_analyzed
        assert payload["meta"]["rows_dropped"] == dataset.rows_dropped
        assert payload["meta"]["warmup_candles"] == dataset.warmup_candles
        assert payload["pipeline_version"]

    def test_timestamps_are_iso_utc_with_a_literal_z(self, dataset: FeatureDataset) -> None:
        payload = json.loads(to_json(dataset))
        assert payload["data"][0]["timestamp"].endswith("Z")
        assert payload["generated_at"].endswith("Z")

    def test_preserves_nulls_as_json_null(self, builder: FeatureDatasetBuilder) -> None:
        untrimmed = builder.build(
            "ETHUSD",
            "1h",
            candles(4),
            [FeatureRequest("sma", {"period": "2"})],
            drop_warmup=False,
        )
        payload = json.loads(to_json(untrimmed))
        assert payload["data"][0]["sma_2"] is None

    def test_output_is_valid_json(self, dataset: FeatureDataset) -> None:
        json.loads(to_json(dataset))  # raises if not


class TestFilename:
    def test_names_the_market_timeframe_and_time(self, dataset: FeatureDataset) -> None:
        name = dataset_filename(dataset, "csv")
        assert name.startswith("ETHUSD-1h-features-")
        assert name.endswith(".csv")

    def test_sanitizes_a_symbol_containing_path_characters(self, dataset: FeatureDataset) -> None:
        unsafe = replace(dataset, symbol="ETH/USD")
        assert "/" not in dataset_filename(unsafe, "json")

    def test_extension_follows_the_format(self, dataset: FeatureDataset) -> None:
        assert dataset_filename(dataset, "json").endswith(".json")

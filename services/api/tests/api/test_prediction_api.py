"""Live Prediction Service REST endpoint tests.

Runs against the real FastAPI app over ASGI with the in-memory SQLite
database, mirroring `test_training_api.py`/`test_evaluation_api.py`'s own
convention exactly — including reusing their `seed_real_candles`/
`create_experiment_with_real_config`/`job_body` helpers rather than a
second copy of any of them.
"""

from datetime import UTC, datetime, timedelta

import httpx

from app.dependencies.prediction import get_prediction_service
from tests.api.test_training_api import (
    create_experiment,
    create_experiment_with_real_config,
    job_body,
    run_and_wait,
    seed_real_candles,
)
from tests.conftest import SessionFactory

#: Well within `seed_real_candles`'s own 80-hour seeded series (starting
#: 2026-01-01T00:00), leaving real candles already stored past a horizon
#: of 1 — gradeable immediately, unlike a prediction at the very latest one.
_EARLY_AS_OF = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=70)


async def train_completed_job(
    client: httpx.AsyncClient,
    session_factory: SessionFactory,
    *,
    symbol: str,
    model_type: str = "logistic_regression",
    target: str = "next_direction",
) -> dict:
    await seed_real_candles(session_factory, symbol=symbol)
    experiment = await create_experiment_with_real_config(client, target=target)
    created = (
        await client.post(
            "/api/v1/training-jobs",
            json=job_body(experiment["id"], model_type=model_type, symbol=symbol, timeframe="1h"),
        )
    ).json()
    # `run_and_wait` (not a bare POST) — `/run` no longer blocks for the pipeline's
    # duration, see `test_training_api.py`'s own module docstring.
    body = await run_and_wait(client, created["id"])
    assert body["status"] == "completed", body
    return body


class TestRunPrediction:
    async def test_runs_and_returns_a_labeled_prediction(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        job = await train_completed_job(client, session_factory, symbol="APIPREDUSD")

        response = await client.post(
            "/api/v1/predictions/run",
            json={"training_job_id": job["id"], "symbol": "APIPREDUSD"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["training_job_id"] == job["id"]
        assert body["symbol"] == "APIPREDUSD"
        assert body["target_column"] == "next_direction_1"
        assert body["horizon"] == 1
        assert body["predicted_value"] in {"up", "down", "flat"}
        assert body["confidence"] is not None
        assert 0.0 <= body["confidence"] <= 1.0
        assert body["confidence_unavailable_reason"] is None
        assert body["actual_outcome"] is None
        assert body["as_of"]

    async def test_is_also_mounted_unversioned(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        job = await train_completed_job(client, session_factory, symbol="APIUNVERSUSD")

        response = await client.post(
            "/predictions/run",
            json={"training_job_id": job["id"], "symbol": "APIUNVERSUSD"},
        )
        assert response.status_code == 201

    async def test_a_regressor_has_no_confidence_and_an_explained_reason(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        job = await train_completed_job(
            client,
            session_factory,
            symbol="APIREGUSD",
            model_type="linear_regression",
            target="next_close",
        )

        response = await client.post(
            "/api/v1/predictions/run",
            json={"training_job_id": job["id"], "symbol": "APIREGUSD"},
        )

        assert response.status_code == 201
        body = response.json()
        assert isinstance(body["predicted_value"], int | float)
        assert body["confidence"] is None
        assert "does not produce class probabilities" in body["confidence_unavailable_reason"]

    async def test_404s_for_an_unknown_training_job(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/api/v1/predictions/run",
            json={
                "training_job_id": "6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90",
                "symbol": "ETHUSD",
            },
        )
        assert response.status_code == 404
        assert response.json()["code"] == "training_job_not_found"

    async def test_409s_for_a_job_that_has_not_completed_yet(
        self, client: httpx.AsyncClient
    ) -> None:
        experiment = await create_experiment(client)
        created = (
            await client.post("/api/v1/training-jobs", json=job_body(experiment["id"]))
        ).json()

        response = await client.post(
            "/api/v1/predictions/run",
            json={"training_job_id": created["id"], "symbol": "ETHUSD"},
        )

        assert response.status_code == 409
        assert response.json()["code"] == "prediction_not_available"

    async def test_409s_for_a_job_with_no_recorded_artifact(
        self, client: httpx.AsyncClient
    ) -> None:
        """The `placeholder` adapter completes but records no `artifact_uri` a
        prediction could ever load."""
        experiment = await create_experiment(client, dataset_version="ds-placeholder")
        created = (
            await client.post("/api/v1/training-jobs", json=job_body(experiment["id"]))
        ).json()
        run = await run_and_wait(client, created["id"])
        assert run["status"] == "completed"

        response = await client.post(
            "/api/v1/predictions/run",
            json={"training_job_id": created["id"], "symbol": "ETHUSD"},
        )

        # `placeholder` completes with a fabricated `artifact_uri` (it always
        # records one, even though it trains nothing real) — so this job is
        # instead rejected one check later, for having no real feature_columns
        # to reconstruct a live vector from.
        assert response.status_code == 409
        assert response.json()["code"] == "live_feature_reconstruction_not_supported"

    async def test_404s_for_an_unknown_market(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        job = await train_completed_job(client, session_factory, symbol="APIKNOWNUSD")

        response = await client.post(
            "/api/v1/predictions/run",
            json={"training_job_id": job["id"], "symbol": "DOES-NOT-EXIST"},
        )

        assert response.status_code == 404
        assert response.json()["code"] == "market_not_found"


class TestGetPrediction:
    async def test_reopens_a_persisted_prediction(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        job = await train_completed_job(client, session_factory, symbol="APIGETUSD")
        created = (
            await client.post(
                "/api/v1/predictions/run",
                json={"training_job_id": job["id"], "symbol": "APIGETUSD"},
            )
        ).json()

        response = await client.get(f"/api/v1/predictions/{created['id']}")

        assert response.status_code == 200
        assert response.json()["id"] == created["id"]
        assert response.json()["predicted_value"] == created["predicted_value"]

    async def test_404s_for_an_unknown_prediction_id(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/predictions/6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90")
        assert response.status_code == 404
        assert response.json()["code"] == "prediction_not_found"


class TestListPredictions:
    async def test_lists_and_filters_by_training_job(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        job = await train_completed_job(client, session_factory, symbol="APILISTUSD")
        created = (
            await client.post(
                "/api/v1/predictions/run",
                json={"training_job_id": job["id"], "symbol": "APILISTUSD"},
            )
        ).json()

        response = await client.get("/api/v1/predictions", params={"training_job_id": job["id"]})

        assert response.status_code == 200
        body = response.json()
        assert body["total"] >= 1
        assert any(p["id"] == created["id"] for p in body["predictions"])

    async def test_filters_by_symbol_that_matches_nothing(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/predictions", params={"symbol": "NOPE"})
        assert response.status_code == 200
        assert response.json()["total"] == 0

    async def test_rejects_an_invalid_sort_column(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/predictions", params={"sort": "not-a-column"})
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_prediction_sort"


class TestGradedResponseShape:
    """`actual_outcome`/`is_correct`/`error`/`graded_at`/`available_after` —
    grading itself has no HTTP trigger (it's scheduler/script-only, see
    `ARCHITECTURE.md` § "Machine Learning Training Framework"'s own
    background-task precedent applied here), so these tests advance state
    the same way `test_training_api.py`'s own `wait_for_in_flight_training_jobs`
    does: call the service directly, then verify the *HTTP response* reflects
    it — proving the wiring, not re-testing grading logic itself (already
    covered by `tests/prediction/test_grading.py`/`test_service.py`).
    """

    async def test_get_shows_pending_fields_before_grading(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        job = await train_completed_job(client, session_factory, symbol="APIPENDINGUSD")
        created = (
            await client.post(
                "/api/v1/predictions/run",
                json={"training_job_id": job["id"], "symbol": "APIPENDINGUSD"},
            )
        ).json()

        response = await client.get(f"/api/v1/predictions/{created['id']}")

        assert response.status_code == 200
        body = response.json()
        assert body["actual_outcome"] is None
        assert body["is_correct"] is None
        assert body["error"] is None
        assert body["graded_at"] is None
        assert body["available_after"] is not None

    async def test_get_and_list_show_the_outcome_once_graded(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        job = await train_completed_job(client, session_factory, symbol="APIGRADEDUSD")
        created = (
            await client.post(
                "/api/v1/predictions/run",
                json={
                    "training_job_id": job["id"],
                    "symbol": "APIGRADEDUSD",
                    "as_of": _EARLY_AS_OF.isoformat(),
                },
            )
        ).json()

        service = get_prediction_service(session_factory())
        summary = await service.grade_pending()
        assert summary.graded == 1

        get_response = await client.get(f"/api/v1/predictions/{created['id']}")
        get_body = get_response.json()
        assert get_body["actual_outcome"] in {"up", "down", "flat"}
        assert get_body["is_correct"] in {True, False}
        assert get_body["error"] is None
        assert get_body["graded_at"] is not None
        assert get_body["available_after"] is None

        list_response = await client.get(
            "/api/v1/predictions", params={"training_job_id": job["id"]}
        )
        listed = next(p for p in list_response.json()["predictions"] if p["id"] == created["id"])
        assert listed["actual_outcome"] == get_body["actual_outcome"]
        assert listed["is_correct"] == get_body["is_correct"]
        assert listed["graded_at"] == get_body["graded_at"]

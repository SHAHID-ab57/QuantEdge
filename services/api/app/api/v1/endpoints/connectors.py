"""External Data Connectors read API — backs the Data Sources page
(M4-E1-T3, `ARCHITECTURE.md` § "External Data Connectors").

Two surfaces, both read-only (ingestion stays internal — a scheduler and
a backfill script, never triggered over HTTP):

- ``GET /connectors`` publishes the registry as a catalogue, each entry
  carrying its own most recent value, mirroring ``/features``'s own
  "reads straight from the registry, nothing hardcoded" contract.
- ``GET /connectors/{source}/history`` returns a paginated time series
  for charting, mirroring ``/candles``'s own limit/offset conventions.
"""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, status

from app.dependencies.connectors import get_connector_service
from app.schemas.connectors import ConnectorCatalogResponse, ConnectorHistoryResponse
from app.services.connectors import DEFAULT_HISTORY_LIMIT, MAX_HISTORY_LIMIT, ConnectorService

router = APIRouter(tags=["connectors"])

ConnectorServiceDep = Annotated[ConnectorService, Depends(get_connector_service)]
SourcePath = Annotated[
    str, Path(examples=["fear_greed"], description="Registered connector source")
]

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {
        "description": "Unknown connector source",
        "content": {
            "application/json": {
                "examples": {
                    "connector_not_found": {
                        "summary": "No connector is registered under this source name",
                        "value": {
                            "code": "connector_not_found",
                            "detail": (
                                "Connector source 'nope' is not registered; available: fear_greed"
                            ),
                        },
                    },
                }
            }
        },
    },
}


@router.get(
    "/connectors",
    response_model=ConnectorCatalogResponse,
    summary="List registered external data connectors",
    description=(
        "Return every registered connector with its most recent value. A "
        "connector registered but never ingested reports null latest "
        "value/timestamp rather than an error."
    ),
)
async def list_connectors(service: ConnectorServiceDep) -> ConnectorCatalogResponse:
    """Return the connector catalogue."""
    return await service.list_connectors()


@router.get(
    "/connectors/{source}/history",
    response_model=ConnectorHistoryResponse,
    summary="Query one connector's stored history",
    description=(
        "Return a page of stored points for one connector source, oldest "
        "first. start/end are each independently inclusive when given "
        "(this table's own convention — see ExternalDataPoint's own "
        "docstring for why it differs from candles' half-open range); "
        "omit either to leave that side of the range open. Pages use "
        "limit/offset with total/returned/has_more metadata, mirroring "
        "/candles."
    ),
    responses=_ERROR_RESPONSES,
)
async def get_connector_history(
    source: SourcePath,
    service: ConnectorServiceDep,
    start: Annotated[
        datetime | None,
        Query(
            examples=["2026-01-01T00:00:00Z"],
            description="Range start (inclusive), ISO-8601 UTC",
        ),
    ] = None,
    end: Annotated[
        datetime | None,
        Query(
            examples=["2026-02-01T00:00:00Z"],
            description="Range end (inclusive), ISO-8601 UTC",
        ),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=MAX_HISTORY_LIMIT, description="Maximum points per page"),
    ] = DEFAULT_HISTORY_LIMIT,
    offset: Annotated[
        int,
        Query(ge=0, description="Number of points to skip"),
    ] = 0,
) -> ConnectorHistoryResponse:
    """Return a page of one connector's stored history."""
    return await service.get_history(source, start=start, end=end, limit=limit, offset=offset)

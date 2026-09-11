"""Dependency provider for the live market (ticker + funding) endpoint."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends

from app.integrations.delta.client import get_delta_client
from app.runtime import Runtime, get_runtime
from app.services.live_market import LiveMarketService


async def get_live_market_service(
    runtime: Annotated[Runtime, Depends(get_runtime)],
) -> AsyncIterator[LiveMarketService]:
    """Build the live market service over the process-wide state manager.

    The service reads the same :class:`~app.state.manager.MarketStateManager`
    the WebSocket gateway uses. A short-lived Delta REST client backs the
    funding-rate / open-interest fill-in and is closed when the request
    ends.
    """
    client = get_delta_client()
    try:
        yield LiveMarketService(state_manager=runtime.state_manager, delta_client=client)
    finally:
        await client.aclose()

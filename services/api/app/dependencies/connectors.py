"""Dependency providers for the External Data Connectors read API."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.repositories.external_data import ExternalDataRepository
from app.services.connectors import ConnectorService


def get_connector_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ConnectorService:
    """Build the connector service wired to the request session."""
    return ConnectorService(external_data_repository=ExternalDataRepository(session))

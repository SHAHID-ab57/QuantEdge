"""Dependency providers for the Experiment Management API."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.repositories.experiments import ExperimentRepository
from app.services.experiments import ExperimentService


def get_experiment_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ExperimentService:
    """Build the experiment service wired to the request session."""
    return ExperimentService(repository=ExperimentRepository(session))

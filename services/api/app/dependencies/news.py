"""Dependency providers for the News API."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.repositories.news import NewsRepository
from app.services.news_api import NewsService


def get_news_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> NewsService:
    """Build the news service wired to the request session."""
    return NewsService(news_repository=NewsRepository(session))

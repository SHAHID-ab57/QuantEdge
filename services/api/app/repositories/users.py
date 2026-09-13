"""User account storage access."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    """Create/read access to `users`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, user: User) -> User:
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        """Look up a user by email — the caller normalizes case, this
        method does an exact, case-sensitive match against the stored
        (already-lowercased) value."""
        stmt = select(User).where(User.email == email)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def count(self) -> int:
        """How many users exist — the CLI's own "first user" messaging reads this."""
        stmt = select(func.count()).select_from(User)
        return int((await self.session.execute(stmt)).scalar_one())

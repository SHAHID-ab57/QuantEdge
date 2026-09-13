"""Authentication business logic — the one place a login is checked or a
user is created.

Deliberately thin: `app.auth.security` does the actual hashing/JWT work,
`app.repositories.users.UserRepository` does the actual SQL. This is the
seam that ties the two together with the platform's own conventions
(typed domain errors, no SQL in a router or a CLI script).
"""

import uuid
from dataclasses import dataclass

from app.auth.errors import EmailAlreadyRegisteredError, InvalidCredentialsError
from app.auth.security import create_access_token, hash_password, verify_password
from app.core.config import Settings
from app.models.user import User
from app.repositories.users import UserRepository
from app.schemas.auth import TokenResponse


def normalize_email(email: str) -> str:
    """The one place an email is lowercased before a lookup or an insert —
    `users.email`'s own uniqueness constraint is case-sensitive at the
    database level, so two logins that differ only by case must resolve
    to the same row here, not rely on the database to catch it."""
    return email.strip().lower()


@dataclass
class AuthService:
    """Login and user-creation logic, shared by the API and the CLI."""

    user_repository: UserRepository
    settings: Settings

    async def login(self, *, email: str, password: str) -> TokenResponse:
        """Verify credentials and issue a fresh bearer token.

        Raises `InvalidCredentialsError` for either an unknown email or a
        wrong password — the same error either way, see that error's own
        docstring for why.
        """
        user = await self.user_repository.get_by_email(normalize_email(email))
        if user is None or not verify_password(password, user.hashed_password):
            raise InvalidCredentialsError()

        token = create_access_token(user_id=user.id, settings=self.settings)
        return TokenResponse(
            access_token=token,
            expires_in=self.settings.jwt_access_token_expire_minutes * 60,
        )

    async def get_user(self, user_id: uuid.UUID) -> User | None:
        return await self.user_repository.get_by_id(user_id)

    async def register(self, *, email: str, password: str) -> User:
        """Create a new user — the CLI's own first-user (and any
        subsequent-user) creation path. Not exposed as an API endpoint:
        this platform's own scope is a small number of real users, added
        by whoever already has server access, not open self-registration.
        """
        normalized = normalize_email(email)
        existing = await self.user_repository.get_by_email(normalized)
        if existing is not None:
            raise EmailAlreadyRegisteredError(normalized)
        user = User(email=normalized, hashed_password=hash_password(password))
        return await self.user_repository.create(user)

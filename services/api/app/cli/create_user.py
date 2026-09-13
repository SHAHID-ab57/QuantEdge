"""Create a user account — the minimal, deliberately un-fancy path this
task's own scope calls for ("a CLI command or a simple registration
endpoint... don't over-build this into a full onboarding flow").

Usage:

    uv run python -m app.cli.create_user someone@example.com

Prompts for a password twice (never taken as an argument — a plaintext
password is not something a shell history should ever hold), hashes it,
and inserts the row. Exits non-zero with a clear message on a duplicate
email, a database that isn't configured, or a password that doesn't meet
`app.auth.security`'s own length limit.
"""

import asyncio
import getpass
import sys

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.auth.errors import EmailAlreadyRegisteredError
from app.core.config import get_settings
from app.db.engine import build_engine, dispose_engine
from app.repositories.users import UserRepository
from app.services.auth import AuthService


async def _create_user(email: str, password: str) -> int:
    settings = get_settings()
    if not settings.database_url:
        print("error: no database configured (DATABASE_URL/DB_URL is unset)", file=sys.stderr)
        return 1

    engine = build_engine()
    try:
        session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with session_factory() as session:
            service = AuthService(user_repository=UserRepository(session), settings=settings)
            try:
                user = await service.register(email=email, password=password)
            except EmailAlreadyRegisteredError as exc:
                print(f"error: {exc.message}", file=sys.stderr)
                return 1
            except ValueError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 1
            print(f"Created user {user.email} ({user.id})")
            return 0
    finally:
        await dispose_engine()


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python -m app.cli.create_user <email>", file=sys.stderr)
        return 2
    email = sys.argv[1]

    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("error: passwords do not match", file=sys.stderr)
        return 1
    if not password:
        print("error: password must not be empty", file=sys.stderr)
        return 1

    return asyncio.run(_create_user(email, password))


if __name__ == "__main__":
    sys.exit(main())

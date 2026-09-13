"""User accounts — basic authentication for a small number of real users.

Deliberately narrow, matching M5-E1-T1's own stated scope: one flat user
table, no organizations, no roles, no permission tiers. Every
authenticated user on this platform can do everything an authenticated
user can do; the distinction this system draws is authenticated vs.
anonymous, not admin vs. member. That is a genuine, stated design
decision (see `ARCHITECTURE.md` § "Authentication & Audit Trail"), not an
oversight — building role-based access control now, with no product
requirement for it yet, would be exactly the kind of premature
infrastructure this project has otherwise been careful to defer.
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, TimestampMixin

__all__ = ["User"]


class User(BaseModel, TimestampMixin):
    """One real person able to log in and act on this platform.

    `hashed_password` is a bcrypt hash (`app.auth.security.hash_password`)
    — never plaintext, never a reversible scheme. `email` is the login
    identifier and is case-sensitively unique at the database level (the
    application layer normalizes to lowercase before every lookup/insert,
    in `app.auth`, so two users can never collide on case alone).
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
        comment="Login identifier, stored lowercased by the application layer.",
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="A bcrypt hash — never plaintext, never a reversible encoding.",
    )

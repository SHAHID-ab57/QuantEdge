"""Domain errors for the dataset validation engine.

``UnknownValidationRuleError`` extends ``AppError`` so the application's
existing exception handler turns it into the same ``{"code", "detail"}``
envelope the rest of the API already uses — no validation-specific error
handling exists in the HTTP layer, matching the features and indicators
engines. ``DuplicateValidationRuleError`` does not: it is a programming
mistake in a rule's own declaration, caught once at import time, never a
condition an HTTP client can trigger — the same split
``app/features/errors.py`` makes between its request-time and startup-time
errors.
"""

from fastapi import status

from app.core.exceptions import AppError


class UnknownValidationRuleError(AppError):
    """Raised when a caller names a validation rule that isn't registered."""

    def __init__(self, name: str, available: tuple[str, ...] = ()) -> None:
        suffix = f"; available: {', '.join(available)}" if available else ""
        super().__init__(
            f"Validation rule {name!r} is not registered{suffix}",
            code="validation_rule_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
        self.name = name


class DuplicateValidationRuleError(RuntimeError):
    """Raised at import time when two rules claim the same registry name."""

    def __init__(self, name: str) -> None:
        super().__init__(
            f"A validation rule named {name!r} is already registered; "
            "rule names must be unique across the registry"
        )
        self.name = name

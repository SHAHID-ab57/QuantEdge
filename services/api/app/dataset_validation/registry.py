"""The validation rule registry — the engine's extension point.

Same shape as ``FeatureRegistry``/``IndicatorRegistry`` for the same
reason: a new rule is a subclass decorated with ``@register`` and nothing
else changes. Only one registration style exists here (no
``register_generator``-style instance registration) because, unlike the
moving-average features, no validation rule needs to *wrap* another
already-registered component — every rule is self-contained.
"""

import logging
from collections.abc import Iterator

from app.dataset_validation.base import ValidationRule, ValidationRuleMetadata
from app.dataset_validation.errors import DuplicateValidationRuleError, UnknownValidationRuleError

logger = logging.getLogger("app.dataset_validation.registry")


class ValidationRuleRegistry:
    """A name → rule-instance mapping.

    Rules are instantiated once at registration and reused: they are
    required to be stateless (all state arrives via ``ValidationContext``),
    so one instance can serve every concurrent request without locking.

    Instantiable rather than a module-level singleton so tests — and any
    future caller that needs a restricted rule set, such as a lightweight
    "structural only" gate — can build an isolated registry.
    """

    def __init__(self) -> None:
        self._rules: dict[str, ValidationRule] = {}

    def register(self, rule_cls: type[ValidationRule]) -> type[ValidationRule]:
        """Register a rule class. Usable directly as a decorator.

        Returns the class unchanged so stacking or subclassing still works.
        """
        metadata = getattr(rule_cls, "metadata", None)
        if metadata is None:
            raise TypeError(
                f"{rule_cls.__name__} must declare a class-level "
                "`metadata: ValidationRuleMetadata` to be registered"
            )
        name = metadata.name
        if name in self._rules:
            raise DuplicateValidationRuleError(name)
        self._rules[name] = rule_cls()
        logger.debug("Registered validation rule %r (%s)", name, rule_cls.__name__)
        return rule_cls

    def get(self, name: str) -> ValidationRule:
        """Resolve a rule by name, or raise a 404 domain error."""
        rule = self._rules.get(name)
        if rule is None:
            raise UnknownValidationRuleError(name, self.names())
        return rule

    def has(self, name: str) -> bool:
        """Whether a rule with this name is registered."""
        return name in self._rules

    def names(self) -> tuple[str, ...]:
        """Every registered name, sorted for a stable catalogue order."""
        return tuple(sorted(self._rules))

    def describe_all(self) -> list[ValidationRuleMetadata]:
        """Metadata for every registered rule, sorted by name."""
        return [self._rules[name].metadata for name in self.names()]

    def __len__(self) -> int:
        return len(self._rules)

    def __iter__(self) -> Iterator[ValidationRule]:
        return (self._rules[name] for name in self.names())


#: The registry the application uses. Builtin rules register into this one
#: at import time; ``get_dataset_validator`` serves it to the API.
default_registry = ValidationRuleRegistry()


def register(rule_cls: type[ValidationRule]) -> type[ValidationRule]:
    """Register a rule class into the application's default registry."""
    return default_registry.register(rule_cls)

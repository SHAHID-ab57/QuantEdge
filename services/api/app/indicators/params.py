"""Declarative parameter specifications and their validation.

An indicator declares *what* parameters it accepts; this module owns *how*
those declarations are checked and coerced. Keeping the two apart is what
lets a new indicator be added without touching the engine: the engine
validates against whatever specs the indicator declares, with no knowledge
of any particular indicator's parameters.

Values arrive as strings from the query layer (see the indicators REST
endpoints), so coercion is part of validation rather than a separate step
the caller has to remember.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from app.indicators.errors import InvalidIndicatorParameterError

ParameterType = Literal["int", "float", "string", "bool"]

_TRUE = frozenset({"true", "1", "yes", "on"})
_FALSE = frozenset({"false", "0", "no", "off"})


@dataclass(frozen=True, slots=True)
class ParameterSpec:
    """One parameter an indicator accepts.

    ``default`` being ``None`` marks the parameter as required. ``minimum``/
    ``maximum`` are inclusive and only meaningful for numeric types;
    ``choices`` restricts a string parameter to a fixed set (e.g. which
    price series to compute over).
    """

    name: str
    type: ParameterType
    label: str
    description: str
    default: Any = None
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] = field(default_factory=tuple)

    @property
    def required(self) -> bool:
        """A parameter with no default must be supplied by the caller."""
        return self.default is None

    def coerce(self, raw: Any) -> Any:
        """Coerce ``raw`` to this spec's type and enforce its constraints.

        Raises ``InvalidIndicatorParameterError`` with a message naming the
        parameter and the actual constraint, so a UI can surface it directly
        against the offending form field.
        """
        value = self._to_type(raw)
        self._check_bounds(value)
        self._check_choices(value)
        return value

    def _to_type(self, raw: Any) -> Any:
        if self.type == "bool":
            return self._to_bool(raw)
        if self.type == "string":
            return str(raw)
        try:
            return int(raw) if self.type == "int" else float(raw)
        except (TypeError, ValueError) as exc:
            raise InvalidIndicatorParameterError(
                self.name, f"expected {self.type}, got {raw!r}"
            ) from exc

    def _to_bool(self, raw: Any) -> bool:
        if isinstance(raw, bool):
            return raw
        text = str(raw).strip().lower()
        if text in _TRUE:
            return True
        if text in _FALSE:
            return False
        raise InvalidIndicatorParameterError(self.name, f"expected a boolean, got {raw!r}")

    def _check_bounds(self, value: Any) -> None:
        if self.type not in {"int", "float"}:
            return
        if self.minimum is not None and value < self.minimum:
            raise InvalidIndicatorParameterError(
                self.name, f"must be >= {_number(self.minimum)}, got {_number(value)}"
            )
        if self.maximum is not None and value > self.maximum:
            raise InvalidIndicatorParameterError(
                self.name, f"must be <= {_number(self.maximum)}, got {_number(value)}"
            )

    def _check_choices(self, value: Any) -> None:
        if self.choices and value not in self.choices:
            allowed = ", ".join(self.choices)
            raise InvalidIndicatorParameterError(
                self.name, f"must be one of: {allowed} (got {value!r})"
            )


def validate_parameters(
    specs: Sequence[ParameterSpec],
    raw: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate ``raw`` against ``specs``, returning a coerced parameter map.

    Rejects unknown keys rather than ignoring them: a typo'd parameter that
    silently falls back to a default would produce a plausible-looking but
    wrong result, which is the worst outcome for a research tool. Missing
    optional parameters are filled from their declared defaults, so the
    returned map is always complete.
    """
    by_name = {spec.name: spec for spec in specs}
    unknown = sorted(set(raw) - set(by_name))
    if unknown:
        known = ", ".join(sorted(by_name)) or "none"
        raise InvalidIndicatorParameterError(
            unknown[0], f"is not accepted by this indicator; it accepts: {known}"
        )

    resolved: dict[str, Any] = {}
    for spec in specs:
        if spec.name in raw:
            resolved[spec.name] = spec.coerce(raw[spec.name])
        elif spec.required:
            raise InvalidIndicatorParameterError(spec.name, "is required")
        else:
            resolved[spec.name] = spec.default
    return resolved


def _number(value: float) -> str:
    """Render a bound without a misleading trailing ``.0`` on whole numbers."""
    if isinstance(value, int) or value.is_integer():
        return str(int(value))
    return str(value)

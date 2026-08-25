"""Response schemas (DTOs) for the dataset validation API.

The engine's own dataclasses (``ValidationReport``, ``ValidationIssue``, …)
are deliberately Pydantic-free so rules stay independent of the web layer;
this module is the one place those are mapped to the wire — the same split
``app/schemas/features.py`` and ``app/schemas/indicators.py`` already make.

``DatasetValidationRequest`` is a ``FeatureDatasetRequest`` (imported, not
redeclared) plus two validation-only fields. Subclassing rather than
duplicating the market/timeframe/range/feature-selection fields is what
lets the exact same request body that builds a dataset also validate it —
a caller changes only the URL, not the shape of what they send.
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_serializer

from app.dataset_validation.base import ValidationIssue, ValidationRuleMetadata
from app.dataset_validation.report import CategorySummary, ValidationReport, ValidationSummary
from app.schemas.features import FeatureDatasetRequest


class DatasetValidationRequest(FeatureDatasetRequest):
    """Everything needed to build a dataset, plus what to validate it against."""

    required_columns: list[str] = Field(
        default_factory=list,
        description="Column names that must be present, beyond what the features imply",
    )
    rules: list[str] | None = Field(
        default=None,
        description="Run only these rule names; omit to run every registered rule",
    )


class ValidationIssueDTO(BaseModel):
    """One finding from one rule."""

    rule: str
    category: str
    severity: str
    code: str
    message: str
    column: str | None = None
    row_index: int | None = None
    count: int | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_issue(cls, issue: ValidationIssue) -> "ValidationIssueDTO":
        """Map an engine ``ValidationIssue`` onto the wire DTO."""
        return cls(
            rule=issue.rule,
            category=issue.category,
            severity=issue.severity,
            code=issue.code,
            message=issue.message,
            column=issue.column,
            row_index=issue.row_index,
            count=issue.count,
            details=issue.details,
        )


class ValidationSummaryDTO(BaseModel):
    """Headline counts across every issue found, regardless of category."""

    total_checks: int
    errors: int
    warnings: int
    info: int

    @classmethod
    def from_summary(cls, summary: ValidationSummary) -> "ValidationSummaryDTO":
        """Map an engine ``ValidationSummary`` onto the wire DTO."""
        return cls(
            total_checks=summary.total_checks,
            errors=summary.errors,
            warnings=summary.warnings,
            info=summary.info,
        )


class CategorySummaryDTO(BaseModel):
    """Issue counts scoped to one validation category."""

    errors: int
    warnings: int
    info: int

    @classmethod
    def from_summary(cls, summary: CategorySummary) -> "CategorySummaryDTO":
        """Map an engine ``CategorySummary`` onto the wire DTO."""
        return cls(errors=summary.errors, warnings=summary.warnings, info=summary.info)


class ValidationReportResponse(BaseModel):
    """The outcome of validating one dataset: pass/fail, every issue, and how long it took."""

    dataset_id: str = Field(..., description="The validated dataset's own unique build id")
    symbol: str
    timeframe: str
    engine_version: str = Field(
        ..., description="Version of the validation engine itself, independent of any rule's own"
    )
    validated_at: datetime
    passed: bool = Field(
        ..., description="False only when at least one error-severity issue was found"
    )
    rules_run: list[str] = Field(..., description="Rule names actually run, in run order")
    summary: ValidationSummaryDTO
    categories: dict[str, CategorySummaryDTO] = Field(
        ..., description="Per-category issue counts; every category is present, even at zero"
    )
    issues: list[ValidationIssueDTO]
    rows: int = Field(..., description="Rows in the validated dataset")
    columns: int = Field(..., description="Columns in the validated dataset")
    duration_ms: float = Field(..., description="Wall-clock time spent running every rule")

    @field_serializer("validated_at")
    def _serialize_validated_at(self, value: datetime) -> str:
        """ISO-8601 UTC with a literal ``Z``, matching every timestamp on this API."""
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

    @classmethod
    def from_report(cls, report: ValidationReport) -> "ValidationReportResponse":
        """Map an engine ``ValidationReport`` onto the wire DTO."""
        return cls(
            dataset_id=report.dataset_id,
            symbol=report.symbol,
            timeframe=report.timeframe,
            engine_version=report.engine_version,
            validated_at=report.validated_at,
            passed=report.passed,
            rules_run=list(report.rules_run),
            summary=ValidationSummaryDTO.from_summary(report.summary),
            categories={
                name: CategorySummaryDTO.from_summary(summary)
                for name, summary in report.categories.items()
            },
            issues=[ValidationIssueDTO.from_issue(issue) for issue in report.issues],
            rows=report.rows,
            columns=report.columns,
            duration_ms=report.duration_ms,
        )


class ValidationRuleDTO(BaseModel):
    """One validation rule's catalogue entry."""

    name: str
    category: str
    description: str
    default_severity: str
    version: str

    @classmethod
    def from_metadata(cls, metadata: ValidationRuleMetadata) -> "ValidationRuleDTO":
        """Map engine metadata onto the wire DTO."""
        return cls(
            name=metadata.name,
            category=metadata.category,
            description=metadata.description,
            default_severity=metadata.default_severity,
            version=metadata.version,
        )


class ValidationRuleCatalogResponse(BaseModel):
    """Every validation rule the engine can run."""

    rules: list[ValidationRuleDTO]
    total: int = Field(..., description="Number of registered rules")
    categories: list[str] = Field(
        ..., description="Distinct categories present, for grouping in a UI"
    )

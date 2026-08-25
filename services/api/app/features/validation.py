"""Request-time validation for a dataset build.

Distinct from ``FeatureRegistry.validate_dependencies`` (a startup-time
integrity check over the *whole registry's* dependency graph): this module
checks one *request* — a specific list of features a researcher asked for
together — before any of them run.

Column-collision detection stays in ``dataset.py`` rather than here, since a
column name can only be known once a request's parameters are resolved
(``sma`` at period 20 and period 50 produce different columns), which is
part of actually running the generator. Missing-dependency detection is
checkable from metadata alone, before running anything, so it belongs here,
in the "resolve → validate → ... → generate" pipeline's validate stage.
"""

from typing import TYPE_CHECKING

from app.features.errors import MissingFeatureDependencyError
from app.features.pipeline import FeaturePipeline

if TYPE_CHECKING:
    # Deferred to avoid a runtime cycle: `dataset.py` imports this module.
    from app.features.dataset import FeatureRequest


def validate_feature_requests(pipeline: FeaturePipeline, requests: "list[FeatureRequest]") -> None:
    """Reject a dataset request whose features have unmet dependencies.

    Unknown-feature-name and invalid-parameter errors are deliberately left
    to ``FeaturePipeline.run`` itself (called per-request by the dataset
    builder) rather than duplicated here — this function only adds the one
    check nothing else in the pipeline performs: "is everything this
    feature needs also being requested?" A feature whose name doesn't
    resolve is simply skipped by this check (its own, more specific error
    surfaces when the builder actually runs it).
    """
    requested = {request.feature for request in requests}
    for request in requests:
        if not pipeline.registry.has(request.feature):
            continue
        dependencies = pipeline.describe(request.feature).dependencies
        missing = tuple(dep for dep in dependencies if dep not in requested)
        if missing:
            raise MissingFeatureDependencyError(request.feature, missing)

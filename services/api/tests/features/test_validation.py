"""Request-time dependency validation tests.

Exercised against an isolated registry with purpose-built test generators
(matching the pattern in `test_registry.py`/`test_pipeline.py`), since none
of the shipped generators declare a real dependency today — this is the
request-time half of a documented extension point, not yet exercised by
production traffic.
"""

import pytest

from app.features.base import FeatureContext, FeatureGenerator, FeatureMetadata, FeatureOutput
from app.features.dataset import FeatureRequest
from app.features.errors import MissingFeatureDependencyError
from app.features.pipeline import FeaturePipeline
from app.features.registry import FeatureRegistry
from app.features.validation import validate_feature_requests


def make_generator(name: str, dependencies: tuple[str, ...] = ()) -> type[FeatureGenerator]:
    class _Generator(FeatureGenerator):
        metadata = FeatureMetadata(
            name=name, label=name, description="", category="test", dependencies=dependencies
        )

        def generate(self, ctx: FeatureContext) -> FeatureOutput:
            return FeatureOutput(series=[])

    return _Generator


@pytest.fixture
def pipeline() -> FeaturePipeline:
    registry = FeatureRegistry()
    registry.register(make_generator("base"))
    registry.register(make_generator("derived", dependencies=("base",)))
    registry.register(make_generator("independent"))
    return FeaturePipeline(registry)


class TestMissingDependencies:
    def test_requesting_a_dependent_feature_alone_is_rejected(
        self, pipeline: FeaturePipeline
    ) -> None:
        with pytest.raises(MissingFeatureDependencyError) as exc_info:
            validate_feature_requests(pipeline, [FeatureRequest("derived")])
        assert exc_info.value.code == "missing_feature_dependency"
        assert exc_info.value.feature == "derived"
        assert exc_info.value.missing == ("base",)

    def test_requesting_a_feature_with_its_dependency_passes(
        self, pipeline: FeaturePipeline
    ) -> None:
        validate_feature_requests(
            pipeline, [FeatureRequest("derived"), FeatureRequest("base")]
        )  # must not raise

    def test_dependency_order_within_the_request_does_not_matter(
        self, pipeline: FeaturePipeline
    ) -> None:
        # The dependency only needs to be *present*, not listed first.
        validate_feature_requests(pipeline, [FeatureRequest("base"), FeatureRequest("derived")])

    def test_a_dependency_free_feature_is_unaffected(self, pipeline: FeaturePipeline) -> None:
        validate_feature_requests(pipeline, [FeatureRequest("independent")])

    def test_an_empty_request_list_is_trivially_valid(self, pipeline: FeaturePipeline) -> None:
        validate_feature_requests(pipeline, [])

    def test_an_unresolvable_feature_name_is_left_to_the_pipeline(
        self, pipeline: FeaturePipeline
    ) -> None:
        # This function only adds dependency checking; an unknown feature
        # name is `FeaturePipeline.run`'s concern, not this one's — so it
        # must not raise here even though "ghost" cannot ever succeed.
        validate_feature_requests(pipeline, [FeatureRequest("ghost")])

    def test_error_message_names_the_feature_and_what_it_needs(
        self, pipeline: FeaturePipeline
    ) -> None:
        with pytest.raises(MissingFeatureDependencyError) as exc_info:
            validate_feature_requests(pipeline, [FeatureRequest("derived")])
        assert "derived" in exc_info.value.message
        assert "base" in exc_info.value.message

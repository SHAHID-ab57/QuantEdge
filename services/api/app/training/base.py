"""The model adapter contract: inputs, outputs, metadata, and the base class.

This is the framework's one extension point — "orchestrate future
TensorFlow, PyTorch, and scikit-learn models without being tied to any
specific framework." A concrete integration is a subclass that declares
`metadata` and implements `initialize`/`train`; the pipeline, registry,
service, and API need no changes to support it, the same extension
guarantee `FeatureGenerator`/`TargetGenerator`/`ValidationRule` already make
for their own bounded contexts.

`app/training/adapters/placeholder.py` is the only adapter registered
today. It performs **no real training** — it fabricates deterministic
metrics so the pipeline, lifecycle, and API can be built and tested end to
end before a real framework is wired in.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar


@dataclass(frozen=True, slots=True)
class TrainingDataset:
    """A placeholder handle to "the dataset this job trains over."

    Deliberately thin: this platform's ML Dataset Builder
    (`app/ml_datasets/`) never persists a dataset to a table (see
    `ARCHITECTURE.md` § "ML Dataset Builder"), so there is nothing a
    `dataset_version` string can be loaded *from* — it is a citation, the
    same relationship an `Experiment` has to it. `load_dataset` therefore
    only validates and carries that citation forward; it does not, and
    cannot honestly claim to, read real rows.
    """

    dataset_version: str


@dataclass(frozen=True, slots=True)
class ModelAdapterMetadata:
    """Everything the catalogue knows about a model adapter without running it."""

    name: str
    label: str
    description: str
    #: The (future) ML framework this adapter would wrap, e.g. "tensorflow",
    #: "pytorch", "scikit-learn". The only adapter registered today uses
    #: "placeholder" — there is no real framework behind it yet.
    framework: str
    #: Hyperparameter names this adapter recognizes, purely for a frontend
    #: hyperparameter editor to render fields for — never validated
    #: server-side beyond basic JSON shape, since a real framework's own
    #: hyperparameter space isn't known yet.
    hyperparameter_hints: tuple[str, ...] = field(default_factory=tuple)
    version: str = "1.0.0"


@dataclass(frozen=True, slots=True)
class TrainingResult:
    """What a model adapter's `train` returns: fabricated metrics and a result summary."""

    metrics: dict[str, float]
    artifact_uri: str
    summary: dict[str, Any]


class ModelAdapter(ABC):
    """Base class for every pluggable model adapter (Strategy + Registry)."""

    metadata: ClassVar[ModelAdapterMetadata]

    @abstractmethod
    def initialize(self, hyperparameters: Mapping[str, Any]) -> None:
        """Prepare the adapter for training with the given hyperparameters.

        A real framework integration would build/compile a model here.
        Implementations may raise on invalid hyperparameters; the pipeline
        converts any exception into `ModelInitializationError`.
        """

    @abstractmethod
    def train(self, dataset: TrainingDataset, hyperparameters: Mapping[str, Any]) -> TrainingResult:
        """Run one training pass and return its result.

        Implementations may assume `initialize` already ran successfully.
        The pipeline converts any exception into `TrainingExecutionError`.
        """

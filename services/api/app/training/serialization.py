"""Model serialization abstraction — one seam behind which a fitted model is
saved after training and loaded again for prediction.

This platform has no object storage wired in yet (`ARCHITECTURE.md` §
"Known Limitations"), so `LocalDiskModelSerializer` writes to a local
directory (`Settings.model_artifact_dir`) via `joblib` — the same
persistence mechanism scikit-learn's own documentation recommends for its
estimators. A future S3/object-storage backend implements the same
`ModelSerializer` protocol and swaps in behind `default_serializer` with no
change to any model adapter, which only ever calls `.save`/`.load` — never
touches a path or a `joblib` call directly.

**Portability (production incident, fixed here)**: this used to store
``path.resolve().as_uri()`` — an *absolute* ``file://`` URI baked in at
save time, e.g. ``file:///home/shahid/Documents/ss/services/api/var/
model_artifacts/...``, the training machine's own home directory. Every
row written before this fix is unusable anywhere else: on the production
server, prediction failed with a real ``FileNotFoundError`` for exactly
that laptop-only path. ``save()`` now stores a bare, relative reference
(just the filename `LocalDiskModelSerializer` writes here — or, for
`app.training.artifact_files`, ``reports/<filename>``) and
`resolve_artifact_uri` below resolves it against *this* process's own
``model_artifact_dir`` at read time — so the same database row is correct
on a laptop, in Docker, or on any future machine, as long as the file
exists under that machine's own configured directory. A legacy absolute
``file://`` URI (any row written before this fix, prior to the
normalization migration) is still accepted, defensively — only its
filename is trusted, never the directory it names.
"""

import uuid
from pathlib import Path
from typing import Any, Protocol

import joblib

from app.core.config import get_settings


class ModelSerializer(Protocol):
    """Saves a fitted model, returning a reference that later resolves it back."""

    def save(self, model: Any, name: str) -> str: ...  # pragma: no cover - contract only

    def load(self, uri: str) -> Any: ...  # pragma: no cover - contract only


class LocalDiskModelSerializer:
    """Serializes to a local directory via `joblib.dump`/`joblib.load`."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def save(self, model: Any, name: str) -> str:
        self._directory.mkdir(parents=True, exist_ok=True)
        filename = f"{name}-{uuid.uuid4().hex}.joblib"
        joblib.dump(model, self._directory / filename)
        return filename

    def load(self, uri: str) -> Any:
        return joblib.load(resolve_artifact_uri(uri, base=self._directory))


def _default_directory() -> Path:
    configured = get_settings().model_artifact_dir
    path = Path(configured)
    return path if path.is_absolute() else Path.cwd() / path


def resolve_artifact_uri(uri: str, *, base: Path | None = None) -> Path:
    """Resolve a stored artifact reference against an artifact directory —
    the one fix point every reader (model load/predict, the training-job
    artifact download endpoint) goes through, so there is exactly one
    place that knows how to interpret both the current relative form and
    a legacy absolute ``file://`` URI.

    ``base`` defaults to *this process's own* ``model_artifact_dir``
    (`_default_directory`) — right for callers with no serializer
    instance of their own, like the artifact-download endpoint.
    `LocalDiskModelSerializer.load` passes its own ``self._directory``
    instead, so a serializer built against a custom directory (every
    adapter unit test's own `tmp_path` isolation, confirmed the hard way:
    without this, tests resolved against the real, shared
    `model_artifact_dir` instead of their own throwaway directory) keeps
    resolving against *that* directory, not the global default.

    The relative form (what `save()`/`app.training.artifact_files` write
    now) is a bare filename, optionally under ``reports/`` — joined
    directly onto ``base``. A legacy absolute ``file://`` URI is parsed
    only for its own *filename* (and whether its parent directory was
    named ``reports``); the directory it names is never trusted, since it
    names some other machine's filesystem, not this one — precisely the
    bug this function exists to stop repeating.
    """
    if base is None:
        base = _default_directory()
    if uri.startswith("file://"):
        legacy_path = Path.from_uri(uri)
        if legacy_path.parent.name == "reports":
            return base / "reports" / legacy_path.name
        return base / legacy_path.name
    return base / uri


#: The serializer every real model adapter uses — one process-wide instance,
#: matching `app/training/registry.py`'s own "one shared instance" convention.
default_serializer: ModelSerializer = LocalDiskModelSerializer(_default_directory())

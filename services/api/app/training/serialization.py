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
"""

import uuid
from pathlib import Path
from typing import Any, Protocol

import joblib

from app.core.config import get_settings


class ModelSerializer(Protocol):
    """Saves a fitted model, returning a URI that later resolves it back."""

    def save(self, model: Any, name: str) -> str: ...  # pragma: no cover - contract only

    def load(self, uri: str) -> Any: ...  # pragma: no cover - contract only


class LocalDiskModelSerializer:
    """Serializes to a local directory via `joblib.dump`/`joblib.load`."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def save(self, model: Any, name: str) -> str:
        self._directory.mkdir(parents=True, exist_ok=True)
        path = self._directory / f"{name}-{uuid.uuid4().hex}.joblib"
        joblib.dump(model, path)
        return path.resolve().as_uri()

    def load(self, uri: str) -> Any:
        if not uri.startswith("file://"):
            raise ValueError(f"LocalDiskModelSerializer cannot load a non-file:// uri: {uri!r}")
        return joblib.load(Path.from_uri(uri))


def _default_directory() -> Path:
    configured = get_settings().model_artifact_dir
    path = Path(configured)
    return path if path.is_absolute() else Path.cwd() / path


#: The serializer every real model adapter uses — one process-wide instance,
#: matching `app/training/registry.py`'s own "one shared instance" convention.
default_serializer: ModelSerializer = LocalDiskModelSerializer(_default_directory())

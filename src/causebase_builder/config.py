"""Configurable storage boundaries for local CauseBase production work."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CauseBasePaths:
    """Durable archive, mutable runtime and public-data repository locations."""

    archive_root: Path
    runtime_root: Path
    data_repository_root: Path

    @property
    def source_archive_root(self) -> Path:
        return self.archive_root / "sources"

    @property
    def processed_archive_root(self) -> Path:
        return self.archive_root / "processed"

    @property
    def governed_inputs_root(self) -> Path:
        return self.archive_root / "governed-inputs"

    @property
    def staging_root(self) -> Path:
        return self.runtime_root / "staging"

    def runtime_directories(self) -> tuple[Path, ...]:
        return tuple(self.runtime_root / name for name in ("state", "temp", "cache", "logs", "staging"))

    def initialise_runtime(self) -> None:
        """Create only mutable runtime directories; archive data is created on completed write."""
        for directory in self.runtime_directories():
            directory.mkdir(parents=True, exist_ok=True)


def load_paths(workspace_root: Path | None = None) -> CauseBasePaths:
    """Read paths without creating storage or assuming that repositories equal archives."""
    default_workspace = workspace_root or Path.cwd().resolve().parent
    return CauseBasePaths(
        archive_root=Path(os.environ.get("CAUSEBASE_ARCHIVE_ROOT", default_workspace / "archive")),
        runtime_root=Path(os.environ.get("CAUSEBASE_RUNTIME_ROOT", r"C:\CauseBase-runtime")),
        data_repository_root=Path(
            os.environ.get("CAUSEBASE_DATA_REPOSITORY", default_workspace / "causebase-data")
        ),
    )

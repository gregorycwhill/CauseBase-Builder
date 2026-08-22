"""Configurable storage boundaries for local CharityGraph production work."""

from __future__ import annotations

import os
import warnings
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CharityGraphPaths:
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


def _env(canonical: str, legacy: str, default: str | Path) -> str | Path:
    if canonical in os.environ:
        return os.environ[canonical]
    if legacy in os.environ:
        warnings.warn(
            f"{legacy} is deprecated; use {canonical}. It will be removed at the next pre-1.0 breaking release.",
            DeprecationWarning,
            stacklevel=2,
        )
        return os.environ[legacy]
    return default


def load_paths(workspace_root: Path | None = None) -> CharityGraphPaths:
    """Read paths without creating storage or assuming that repositories equal archives."""
    default_workspace = workspace_root or Path.cwd().resolve().parent
    return CharityGraphPaths(
        archive_root=Path(_env("CHARITYGRAPH_ARCHIVE_ROOT", "CAUSEBASE_ARCHIVE_ROOT", default_workspace / "archive")),
        runtime_root=Path(_env("CHARITYGRAPH_RUNTIME_ROOT", "CAUSEBASE_RUNTIME_ROOT", r"C:\CharityGraph-runtime")),
        data_repository_root=Path(_env("CHARITYGRAPH_DATA_REPOSITORY", "CAUSEBASE_DATA_REPOSITORY", default_workspace / "charitygraph-data")),
    )


# Deliberate source-level compatibility alias; new code must import CharityGraphPaths.
CauseBasePaths = CharityGraphPaths

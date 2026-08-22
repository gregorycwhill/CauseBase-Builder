"""Reject unapproved legacy branding on CharityGraph's active Builder surface."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTIVE = (
    "pyproject.toml",
    "README.md",
    "src/charitygraph/cli.py",
    "src/charitygraph/config.py",
    "config/taxonomies/charitygraph-v0.json",
)
ALLOWED_LEGACY_TOKENS = {
    "causebase_id", "causebase_summary", "causebase_geography", "target_causebase_id",
    "reporting_subject_causebase_id", "similar_causebase_id", "causebase_builder",
    "CAUSEBASE_ARCHIVE_ROOT", "CAUSEBASE_RUNTIME_ROOT", "CAUSEBASE_DATA_REPOSITORY", "CauseBasePaths",
}
LEGACY_CONTEXT = re.compile(r"(?i)legacy|deprecated|historical|immutable|compatib")


def main() -> int:
    errors: list[str] = []
    pattern = re.compile(r"(?i)causebase")
    for relative in ACTIVE:
        path = ROOT / relative
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for match in pattern.finditer(line):
                token = re.search(r"[A-Za-z0-9_]+", line[match.start():])
                if (not token or token.group(0) not in ALLOWED_LEGACY_TOKENS) and not LEGACY_CONTEXT.search(line):
                    errors.append(f"{relative}:{number}: unapproved legacy brand reference")
    if errors:
        print("CharityGraph brand lint failed:", *errors, sep="\n")
        return 1
    print("CharityGraph brand lint passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

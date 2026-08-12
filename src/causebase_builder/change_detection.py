"""Deterministic, dependency-aware refresh decisions.

This module deliberately knows nothing about an LLM.  It is the inexpensive
first gate: a changed revenue value does not invalidate prose or embeddings,
while changed programme text does.  Ambiguous cases can be handed to a bounded
semantic assessor by a caller, using the returned ``undecided`` targets.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


DERIVATIVES = ("summary", "taxonomy", "fundraising", "embedding", "similarities")


@dataclass(frozen=True)
class ChangeProfile:
    changed_dimensions: tuple[str, ...]
    numeric_changes: dict[str, tuple[Any, Any]]
    added: dict[str, list[Any]]
    removed: dict[str, list[Any]]
    input_hash: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "changed_dimensions": list(self.changed_dimensions),
            "numeric_changes": self.numeric_changes,
            "added": self.added,
            "removed": self.removed,
            "input_hash": self.input_hash,
        }


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def build_change_profile(previous: dict[str, Any], current: dict[str, Any]) -> ChangeProfile:
    # Group fields by meaning rather than record layout. This also makes the
    # profile stable if source-native fields are reordered.
    dimensions = {
        "financial": ("financial_records", "financial_metrics"),
        "activities": ("activities", "opportunities"),
        "beneficiaries": ("beneficiaries",),
        "geography": ("geography",),
        "funding": ("funding_sources",),
        "fundraising": ("fundraising_methods", "fundraising_expenditure"),
        "relationships": ("relationships",),
        "classifications": ("classifications",),
        "source_native": ("source_native_records",),
        "descriptive": ("causebase_summary", "organisation_self_description"),
    }
    changed: list[str] = []
    numeric: dict[str, tuple[Any, Any]] = {}
    added: dict[str, list[Any]] = {}
    removed: dict[str, list[Any]] = {}
    for dimension, fields in dimensions.items():
        before = {field: previous.get(field) for field in fields}
        after = {field: current.get(field) for field in fields}
        if _canonical(before) == _canonical(after):
            continue
        changed.append(dimension)
        for field in fields:
            left, right = previous.get(field), current.get(field)
            if isinstance(left, (int, float, str)) and isinstance(right, (int, float, str)) and left != right:
                numeric[field] = (left, right)
            elif isinstance(left, list) and isinstance(right, list):
                left_values, right_values = {_canonical(v): v for v in left}, {_canonical(v): v for v in right}
                if right_values.keys() - left_values.keys():
                    added[field] = [right_values[v] for v in sorted(right_values.keys() - left_values.keys())]
                if left_values.keys() - right_values.keys():
                    removed[field] = [left_values[v] for v in sorted(left_values.keys() - right_values.keys())]
    payload = {"previous": previous, "current": current}
    return ChangeProfile(tuple(changed), numeric, added, removed, hashlib.sha256(_canonical(payload).encode()).hexdigest())


def refresh_targets(profile: ChangeProfile) -> dict[str, str]:
    """Return ``reuse``, ``refresh`` or ``undecided`` for every derivative."""
    changed = set(profile.changed_dimensions)
    decisions = {derivative: "reuse" for derivative in DERIVATIVES}
    if changed & {"activities", "beneficiaries", "geography", "descriptive"}:
        for derivative in ("summary", "taxonomy", "embedding", "similarities"):
            decisions[derivative] = "refresh"
    if "fundraising" in changed:
        decisions["fundraising"] = "refresh"
        decisions["summary"] = "undecided"
    if "funding" in changed:
        decisions["fundraising"] = "refresh"
        decisions["summary"] = "undecided"
    if "relationships" in changed or "classifications" in changed:
        for derivative in ("summary", "taxonomy", "embedding", "similarities"):
            decisions[derivative] = "undecided"
    # Source-native changes only matter if their canonical semantic projection
    # changed; the caller can provide compact changed facts to a semantic gate.
    if changed == {"source_native"}:
        decisions["fundraising"] = "undecided"
    return decisions

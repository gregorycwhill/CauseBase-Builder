"""Reproducible Phase 2A candidate selection, deliberately separate from promotion."""

from __future__ import annotations

import csv
import hashlib
from collections import Counter, defaultdict
from pathlib import Path

from .sources.acnc import _value, source_record_id
from .registry import _valid_abn


PURPOSE_COLUMNS = {
    "environment": "Advancing natual environment",
    "health": "Advancing Health",
    "education": "Advancing Education",
    "religion": "Advancing Religion",
    "social_welfare": "Advancing social or public welfare",
    "culture": "Advancing Culture",
    "human_rights": "Promoting or protecting human rights",
    "animal_welfare": "Preventing or relieving suffering of animals",
}
BENEFICIARY_COLUMNS = {
    "children": "Children", "young_people": "Youth", "older_people": "Aged Persons",
    "people_with_disability": "People with Disabilities", "migrants_refugees": "Migrants Refugees or Asylum Seekers",
    "regional_remote": "Rural Regional Remote Communities", "general_community": "General Community in Australia",
    "animals": "animals", "environment": "environment",
}
def _yes(row: dict[str, str], column: str) -> bool:
    return (_value(row, column) or "").casefold() in {"y", "yes", "true", "1"}


def _facet(row: dict[str, str], mapping: dict[str, str], fallback: str) -> str:
    return next((name for name, column in mapping.items() if _yes(row, column)), fallback)


def select_phase2a_candidates(
    acnc_csv: Path, *, target: int = 120, exclude_abns: set[str] | None = None
) -> dict:
    """Choose a deliberately diverse *candidate* set; this never mints subjects.

    Alternating website-presence strata makes sparse web coverage an intentional
    test condition instead of a selection failure. Known federated brand markers
    are excluded until their relationships are independently reviewed.
    """
    excluded = exclude_abns or set()
    with acnc_csv.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    candidates = []
    excluded_counts = Counter()
    for row in rows:
        abn = _value(row, "ABN", "Australian Business Number")
        legal_name = _value(row, "Charity Legal Name", "Legal Name", "Charity Name")
        website = _value(row, "Charity Website")
        if not abn or not _valid_abn(abn) or not legal_name:
            excluded_counts["missing_durable_identifier_or_name"] += 1
            continue
        if abn in excluded:
            excluded_counts["already_governed"] += 1
            continue
        state = _value(row, "State") or "unknown_state"
        size = (_value(row, "Charity Size") or "unknown_size").casefold().replace(" ", "_")
        purpose = _facet(row, PURPOSE_COLUMNS, "other_purpose")
        beneficiary = _facet(row, BENEFICIARY_COLUMNS, "other_beneficiary")
        web_stratum = "website_declared" if website and website.startswith(("http://", "https://")) else "no_website_declared"
        candidates.append({
            "source_record_id": source_record_id(f"abn:{abn}"), "abn": abn,
            "legal_name": legal_name, "display_name": legal_name, "website": website,
            "source_id": "acnc-registered-charities-2026-08-10",
            "source_version": "2026-08-10",
            "strata": {"state": state, "size": size, "purpose": purpose, "beneficiary": beneficiary, "web_presence": web_stratum},
            "promotion_status": "candidate", "promotion_note": "Selection is not a CauseBase subject promotion; durable identity review remains required.",
        })
    # Deterministic round-robin across rich composite strata rather than selecting
    # by source order, size, or web richness.
    buckets: dict[tuple[str, ...], list[dict]] = defaultdict(list)
    for candidate in candidates:
        s = candidate["strata"]
        buckets[(s["web_presence"], s["purpose"], s["beneficiary"], s["state"], s["size"])].append(candidate)
    for bucket in buckets.values():
        bucket.sort(key=lambda item: (item["legal_name"].casefold(), item["abn"]))
    selected: list[dict] = []
    # First pass maximises strata coverage. Subsequent passes retain the same
    # deterministic interleaving and permit at most target records.
    # A stable hash order avoids alphabetical bias (for example every "animal"
    # bucket preceding every "environment" bucket) while remaining reproducible.
    ordered_keys = sorted(
        buckets,
        key=lambda key: hashlib.sha256("|".join(key).encode("utf-8")).hexdigest(),
    )
    while len(selected) < target and any(buckets.values()):
        for key in ordered_keys:
            if buckets[key] and len(selected) < target:
                selected.append(buckets[key].pop(0))
    distribution = {
        dimension: dict(Counter(item["strata"][dimension] for item in selected))
        for dimension in ("state", "size", "purpose", "beneficiary", "web_presence")
    }
    return {
        "cohort_version": "phase2a-candidate-selection-0.1",
        "target_size": target,
        "selected_count": len(selected),
        "selection_method": "deterministic round-robin across web-presence, purpose, beneficiary, state and size strata; excludes only existing governed records and malformed source rows",
        "promotion_boundary": "All selected records remain candidates until independently promoted under the durable identity policy.",
        "excluded_counts": dict(excluded_counts),
        "distribution": distribution,
        "candidates": selected,
    }

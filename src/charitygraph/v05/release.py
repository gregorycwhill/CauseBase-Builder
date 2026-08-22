"""Deterministic assembly and audit of a public contract 0.5 release."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .models import CapabilityRegistry, ReleaseContext
from .stage import stage_rc4_release
from .validate import validate_v05_fixture_release


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_losslessness(rc4_release: Path, cards: list[dict], source_record_ids: set[str]) -> list[str]:
    """Check that every RC4 domain is canonicalised or retained as legacy data."""
    errors: list[str] = []
    originals = {_load(path)["causebase_id"]: _load(path) for path in (rc4_release / "cards").glob("*.json")}
    if set(originals) != {card["causebase_id"] for card in cards}:
        errors.append("card identity set differs from RC4")
    mappings = {
        "activity_observations": ("activities", "activities"),
        "beneficiary_observations": ("beneficiaries", "beneficiaries"),
        "geography_observations": ("descriptive_geography", "descriptive_geography"),
        "classifications": ("classifications", "classifications"),
        "funding_sources": ("funding_sources", "funding_sources"),
        "fundraising_methods": ("fundraising_methods", "fundraising_methods"),
        "financial_records": ("financial_reports", "financial_records"),
    }
    for card in cards:
        original = originals.get(card["causebase_id"])
        if original is None:
            continue
        legacy = card.get("legacy_unbound", {})
        if legacy and legacy.get("origin_card_sha256") != _sha256(original):
            errors.append(f"{card['causebase_id']}: legacy origin hash mismatch")
        for old_field, (new_field, legacy_field) in mappings.items():
            retained = len(card.get(new_field, [])) + len(legacy.get(legacy_field, []))
            if retained != len(original.get(old_field, [])):
                errors.append(f"{card['causebase_id']}: {old_field} loss ({retained}/{len(original.get(old_field, []))})")
        for field, replacement in (("participation_observations", "participation"), ("programs", "programs")):
            if len(card.get(replacement, [])) != len(original.get(field, [])):
                errors.append(f"{card['causebase_id']}: {field} loss")
        if len(card.get("derivatives", [])) != len(original.get("derivative_assessments", [])):
            errors.append(f"{card['causebase_id']}: derivative lineage loss")
        if not set(card.get("source_record_refs", [])) <= source_record_ids:
            errors.append(f"{card['causebase_id']}: unresolved source-record reference")
    return errors


def assemble_release(rc4_release: Path, output: Path, registry: CapabilityRegistry, context: ReleaseContext) -> dict:
    """Write an inspectable 0.5 candidate release from immutable public RC4 input."""
    if output.exists() and any(output.iterdir()):
        raise ValueError("release output must be empty")
    cards = stage_rc4_release(rc4_release, output, registry, context)
    sources: dict[str, dict] = {}
    source_output = output / "source-records"
    source_output.mkdir(parents=True, exist_ok=True)
    for path in sorted((rc4_release / "source-records").glob("*.json")):
        source = _load(path)
        sources[source["source_record_id"]] = source
        (source_output / path.name).write_text(json.dumps(source, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output / "capability-registry.json").write_text(json.dumps(registry.model_dump(), indent=2) + "\n", encoding="utf-8")
    source_ids = set(sources)
    errors = validate_v05_fixture_release(cards, registry, source_ids)
    errors.extend(audit_losslessness(rc4_release, cards, source_ids))
    artefacts = {}
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            relative = path.relative_to(output).as_posix()
            artefacts[relative] = {"bytes": path.stat().st_size, "sha256": _file_sha256(path)}
    manifest = {
        "dataset": "CauseBase",
        "dataset_version": context.dataset_version,
        "contract_version": "0.5",
        "release_id": context.release_id,
        "based_on_release": context.based_on_release,
        "generated_at": context.generated_at,
        "entity_count": len(cards),
        "source_record_count": len(sources),
        "validation": {"status": "passed" if not errors else "failed", "errors": errors},
        "artefacts": artefacts,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest

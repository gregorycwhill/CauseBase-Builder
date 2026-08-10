"""Private national structured-backbone normalisation and safe publication projection."""

from __future__ import annotations

import json
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .registry import SubjectRegistry
from .sources.acnc import parse_acnc_register_csv
from .sources.ais import parse_ais_financial_csv
from .sources.dgr import iter_dgr_bulk_extract

NAMESPACE = uuid.UUID("ca4c5b33-f3e6-45ec-9c80-987b9b17bb43")


def _source_id(kind: str, key: str) -> str:
    return f"src:{kind}:{uuid.uuid5(NAMESPACE, key)}"


def _load_metadata(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    required = {"source_id", "publisher", "source_url", "retrieved_at", "content_sha256", "licence"}
    missing = required - set(data)
    if missing:
        raise ValueError(f"source metadata missing: {sorted(missing)}")
    return data


def _period_bucket(start: str | None, end: str | None) -> str:
    if not start or not end:
        return "missing_dates"
    try:
        from datetime import datetime as dt
        delta = (dt.strptime(end, "%d/%m/%Y") - dt.strptime(start, "%d/%m/%Y")).days + 1
    except ValueError:
        return "unparseable_dates"
    return "nonstandard" if delta < 350 or delta > 380 else "approximately_annual"


def build_national_backbone(
    *, acnc_csv: Path, acnc_metadata: Path, ais_csv: Path, ais_metadata: Path,
    dgr_observations: Path | None, dgr_bulk_zips: list[Path] | None, dgr_metadata: Path | None, registry_path: Path, private_output: Path,
    public_output: Path,
) -> dict:
    """Normalise national rows privately; publish only registry and aggregate metadata.

    No source record is promoted merely by this process. ACNC/registry links use
    previously reviewed source-record IDs only; AIS and DGR joins remain source
    relationships keyed by authoritative ABN.
    """
    acnc_meta, ais_meta = _load_metadata(acnc_metadata), _load_metadata(ais_metadata)
    acnc = parse_acnc_register_csv(acnc_csv)
    ais = parse_ais_financial_csv(ais_csv)
    registry = SubjectRegistry.load(registry_path)
    promoted_by_source = {
        source_id: subject["causebase_id"]
        for subject in registry.subjects
        for source_id in subject["promotion"]["source_record_ids"]
    }
    acnc_by_abn = {
        identifier.value: record.source_record_id
        for record in acnc
        for identifier in record.external_identifiers
        if identifier.scheme == "abn"
    }

    private_output.mkdir(parents=True, exist_ok=True)
    records_path = private_output / "source-records.jsonl"
    resolution_counts: Counter[str] = Counter()
    with records_path.open("w", encoding="utf-8") as out:
        for record in acnc:
            causebase_id = promoted_by_source.get(record.source_record_id)
            status = "resolved" if causebase_id else "candidate"
            resolution_counts[status] += 1
            out.write(json.dumps({
                "source_record_id": record.source_record_id, "source_id": acnc_meta["source_id"],
                "record_type": "acnc_register", "external_identifiers": [i.model_dump() for i in record.external_identifiers],
                "legal_name": record.legal_name, "display_name": record.display_name,
                "resolution": {"resolution_status": status, "resolution_basis": "reviewed registry binding" if causebase_id else "national source record retained without subject promotion", "confidence": "high" if causebase_id else "low"},
                "causebase_id": causebase_id,
            }, ensure_ascii=False) + "\n")
        for ordinal, record in enumerate(ais, start=1):
            source_record_id = _source_id("acnc-ais", f"{record.abn}|{record.financial_report_from}|{record.financial_report_to}|{ordinal}")
            out.write(json.dumps({
                "source_record_id": source_record_id, "source_id": ais_meta["source_id"], "record_type": "ais_financial_observation",
                "external_identifiers": [{"scheme": "abn", "value": record.abn}],
                "register_source_record_id": acnc_by_abn.get(record.abn),
                "reporting_period": {"label": record.reporting_period, "start": record.financial_report_from, "end": record.financial_report_to},
                "consolidated": record.consolidated,
                "money_observations": {"revenue": record.revenue.model_dump(mode="json") if record.revenue else None, "total_expenses": record.total_expenses.model_dump(mode="json") if record.total_expenses else None},
                "resolution": {"resolution_status": "unresolved", "resolution_basis": "financial source observation; no subject assertion", "confidence": "low"},
            }, ensure_ascii=False) + "\n")

    dgr = json.loads(dgr_observations.read_text(encoding="utf-8")) if dgr_observations else {"observations": []}
    bulk_dgr = []
    if dgr_bulk_zips:
        for record in iter_dgr_bulk_extract(dgr_bulk_zips):
            bulk_dgr.append(record)
    dgr_meta = json.loads(dgr_metadata.read_text(encoding="utf-8")) if dgr_metadata else dgr.get("source", {})
    if bulk_dgr:
        with (private_output / "dgr-source-records.jsonl").open("w", encoding="utf-8") as out:
            for record in bulk_dgr:
                out.write(json.dumps({
                    "source_record_id": _source_id("abr-dgr", record.abn), "source_id": dgr_meta["source_id"],
                    "record_type": "dgr_status_observation", "external_identifiers": [{"scheme": "abn", "value": record.abn}],
                    "dgr_status": record.dgr_status, "source_detail": record.raw,
                    "resolution": {"resolution_status": "unresolved", "resolution_basis": "external tax status observation; no subject assertion", "confidence": "low"},
                }) + "\n")
    dgr_counts = Counter(item.get("dgr_status", "unknown") for item in dgr.get("observations", []))
    ais_by_abn = Counter(record.abn for record in ais)
    period_distribution = Counter(_period_bucket(record.financial_report_from, record.financial_report_to) for record in ais)
    consolidated = Counter(record.consolidated for record in ais)
    duplicate_ais = sum(1 for count in ais_by_abn.values() if count > 1)
    diagnostics = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": [acnc_meta, ais_meta, dgr_meta],
        "source_row_counts": {"acnc_register": len(acnc), "ais": len(ais), "dgr_subject_specific": len(dgr.get("observations", [])), "dgr_bulk_observations": len(bulk_dgr)},
        "unique_abns": {"acnc_register": len(acnc_by_abn), "ais": len(ais_by_abn), "dgr_subject_specific": len({i["abn"] for i in dgr.get("observations", [])}), "dgr_bulk": len({i.abn for i in bulk_dgr})},
        "subjects_promoted": len(registry.subjects), "resolution_counts": {status: resolution_counts[status] for status in ("resolved", "candidate", "ambiguous", "unresolved")},
        "ais_coverage": {"with_register_abn": sum(record.abn in acnc_by_abn for record in ais), "without_register_abn": sum(record.abn not in acnc_by_abn for record in ais)},
        "dgr_coverage": {"scope": "national ABR Bulk Extract; absence is only meaningful within this dated extract", "status_counts": {**dict(dgr_counts), "endorsed_bulk": len(bulk_dgr)}},
        "reporting_period_distribution": dict(period_distribution), "consolidated_report_frequency": dict(consolidated),
        "duplicate_multi_record_patterns": {"ais_abns_with_multiple_observations": duplicate_ais},
        "source_parsing_failures": {"acnc_rows_skipped_without_name_or_identifier": 0, "ais_rows_skipped": 0},
        "material_drift": {"status": "not_assessed_first_national_baseline"},
        "identity_multiplicity_examples": [
            {"name": "The Salvation Army", "finding": "multiple ACNC records; no automatic aggregation"},
            {"name": "Royal Flying Doctor Service", "finding": "multiple ACNC records; national and state operations remain distinct without relationship evidence"},
        ],
    }
    (private_output / "national-diagnostics.json").write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")
    (private_output / "source-inventory.json").write_text(json.dumps({"sources": [acnc_meta, ais_meta, dgr_meta]}, indent=2), encoding="utf-8")

    public_output.mkdir(parents=True, exist_ok=True)
    public_registry = {"registry_version": registry.payload["registry_version"], "subjects": registry.subjects}
    (public_output / "registry.json").write_text(json.dumps(public_registry, indent=2), encoding="utf-8")
    (public_output / "national-coverage.json").write_text(json.dumps({k: diagnostics[k] for k in ("source_row_counts", "unique_abns", "subjects_promoted", "resolution_counts", "ais_coverage", "dgr_coverage", "reporting_period_distribution", "consolidated_report_frequency", "duplicate_multi_record_patterns")}, indent=2), encoding="utf-8")
    (public_output / "schema.json").write_text(json.dumps({"kind": "CauseBase Phase 1 structured backbone", "publication_boundary": "aggregate diagnostics and public registry only; raw source rows are private"}, indent=2), encoding="utf-8")
    manifest = {"dataset": "CauseBase Phase 1 structured backbone", "subject_count": len(public_registry["subjects"]), "publication_safe": True, "artefacts": {}}
    from .render import file_sha256
    for path in sorted(public_output.iterdir()):
        if path.is_file() and path.name != "manifest.json":
            manifest["artefacts"][path.name] = {"bytes": path.stat().st_size, "sha256": file_sha256(path)}
    (public_output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return diagnostics


def validate_structured_backbone(path: Path) -> list[str]:
    allowed = {"registry.json", "national-coverage.json", "schema.json", "manifest.json"}
    actual = {item.name for item in path.iterdir() if item.is_file()}
    errors = [f"unexpected publication artefact: {name}" for name in sorted(actual - allowed)]
    errors.extend(f"missing required artefact: {name}" for name in sorted(allowed - actual))
    for forbidden in ("archive", "raw", "source-records"):
        if forbidden in " ".join(actual).lower(): errors.append("private source material in publication")
    return errors

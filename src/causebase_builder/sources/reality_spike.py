"""Conservative, auditable resolution of reality-spike discovery seeds."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .acnc import AcncRegisterRecord, parse_acnc_register_csv
from .ais import parse_ais_financial_csv


def normalise_name(value: str) -> str:
    """Normalise only for candidate discovery, never for asserting identity."""
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def resolve_seed(seed: dict, records: list[AcncRegisterRecord]) -> dict:
    name = seed["name"]
    key = normalise_name(name)
    exact_matches = [
        record
        for record in records
        if key in {normalise_name(record.legal_name), normalise_name(record.display_name)}
    ]
    # A contained brand phrase is candidate discovery only. It is useful for
    # surfacing federated structures, but never sufficient to resolve a subject.
    matches = exact_matches or [
        record
        for record in records
        if len(key) >= 8
        and (key in normalise_name(record.legal_name) or key in normalise_name(record.display_name))
    ]
    candidates = [
        {
            "source_record_id": record.source_record_id,
            "legal_name": record.legal_name,
            "display_name": record.display_name,
            "external_identifiers": [item.model_dump(mode="json") for item in record.external_identifiers],
        }
        for record in matches
    ]
    if not candidates:
        status, confidence, review = "unresolved", "low", "pending"
        basis = "no exact normalised legal or display-name match in this ACNC extract"
    elif len(candidates) == 1:
        # A discovery seed supplies no authoritative ID, address or independent
        # corroboration, so even an exact name remains a reviewable candidate.
        status, confidence, review = "candidate", "medium", "pending"
        basis = (
            "one exact normalised legal/display-name match; no authoritative seed identifier"
            if exact_matches
            else "one contained brand-name match; no authoritative seed identifier"
        )
    else:
        status, confidence, review = "ambiguous", "medium", "pending"
        basis = (
            "multiple exact normalised legal/display-name matches"
            if exact_matches
            else "multiple contained brand-name matches; likely brand/group structure"
        )
    return {
        "seed_name": name,
        "cases": seed.get("cases", []),
        "resolution_status": status,
        "resolution_basis": basis,
        "confidence": confidence,
        "supporting_signals": [
            "exact normalised name" if exact_matches else "contained brand name"
        ] if candidates else [],
        "conflicting_signals": ["multiple source records"] if len(candidates) > 1 else [],
        "review_status": review,
        "candidates": candidates,
    }


def resolve_cohort(
    cohort_path: Path, acnc_csv_path: Path, source_inventory_path: Path | None = None,
    identifier_evidence_path: Path | None = None,
) -> dict:
    cohort = json.loads(cohort_path.read_text(encoding="utf-8"))
    records = parse_acnc_register_csv(acnc_csv_path)
    records_by_abn = {
        item.value: record
        for record in records
        for item in record.external_identifiers
        if item.scheme == "abn"
    }
    results = [resolve_seed(seed, records) for seed in cohort["candidates"]]
    if identifier_evidence_path:
        overrides = json.loads(identifier_evidence_path.read_text(encoding="utf-8"))["overrides"]
        for result in results:
            for override in overrides:
                if override["seed_name"] != result["seed_name"]:
                    continue
                if not result["candidates"] and override["abn"] in records_by_abn:
                    record = records_by_abn[override["abn"]]
                    result["candidates"] = [{"source_record_id": record.source_record_id, "legal_name": record.legal_name, "display_name": record.display_name, "external_identifiers": [item.model_dump(mode="json") for item in record.external_identifiers]}]
                matches = [
                    candidate for candidate in result["candidates"]
                    if any(item["scheme"] == "abn" and item["value"] == override["abn"] for item in candidate["external_identifiers"])
                ]
                if len(matches) == 1:
                    result.update({"resolution_status": "resolved", "resolution_basis": override["basis"], "confidence": override["confidence"], "supporting_signals": [f"ABN:{override['abn']}", override["source"]], "conflicting_signals": [], "review_status": "not_required"})
    if source_inventory_path:
        inventory_rows = json.loads(source_inventory_path.read_text(encoding="utf-8")).get("sources", [])
        for result in results:
            seed_key = normalise_name(result["seed_name"])
            inventory_abns = {entry["external_identifier"]["value"] for entry in inventory_rows if entry.get("external_identifier", {}).get("scheme") == "abn" and (seed_key in normalise_name(entry.get("causebase_subject_seed", "")) or normalise_name(entry.get("causebase_subject_seed", "")) in seed_key)}
            candidate_abns = {
                identifier["value"]
                for candidate in result["candidates"]
                for identifier in candidate["external_identifiers"]
                if identifier["scheme"] == "abn"
            }
            matched_abns = inventory_abns & candidate_abns
            if len(matched_abns) == 1:
                result.update(
                    {
                        "resolution_status": "resolved",
                        "resolution_basis": "curated source inventory ABN matched uniquely to ACNC Register candidate",
                        "confidence": "high",
                        "supporting_signals": [f"ABN:{next(iter(matched_abns))}", "curated source inventory"],
                        "conflicting_signals": [],
                        "review_status": "not_required",
                    }
                )
    counts = {
        status: sum(result["resolution_status"] == status for result in results)
        for status in ("resolved", "candidate", "ambiguous", "unresolved")
    }
    return {
        "cohort_status": cohort["status"],
        "source_record_count": len(records),
        "resolution_counts": counts,
        "results": results,
    }


def map_ais_coverage(resolution_report_path: Path, ais_csv_path: Path) -> dict:
    """Map source candidates to AIS records without promoting them to subjects."""
    resolution = json.loads(resolution_report_path.read_text(encoding="utf-8"))
    ais_by_abn = {record.abn: record for record in parse_ais_financial_csv(ais_csv_path)}
    rows = []
    for result in resolution["results"]:
        abns = [
            identifier["value"]
            for candidate in result["candidates"]
            for identifier in candidate["external_identifiers"]
            if identifier["scheme"] == "abn"
        ]
        matches = [ais_by_abn[abn] for abn in abns if abn in ais_by_abn]
        rows.append(
            {
                "seed_name": result["seed_name"],
                "resolution_status": result["resolution_status"],
                "candidate_abns": abns,
                "financial_coverage_status": "observed" if matches else "not_found_in_source",
                "records": [
                    {
                        "abn": record.abn,
                        "reporting_period_label": record.reporting_period,
                        "period_start": record.financial_report_from,
                        "period_end": record.financial_report_to,
                        "consolidated": record.consolidated,
                        "revenue": record.revenue.model_dump(mode="json") if record.revenue else None,
                        "total_expenses": record.total_expenses.model_dump(mode="json") if record.total_expenses else None,
                    }
                    for record in matches
                ],
            }
        )
    return {
        "source": "ACNC AIS 2023 extract",
        "coverage_counts": {
            status: sum(row["financial_coverage_status"] == status for row in rows)
            for status in ("observed", "not_found_in_source")
        },
        "rows": rows,
    }


def resolve_report_abns(
    extract_paths: list[Path], acnc_csv_path: Path, source_inventory_path: Path | None = None
) -> dict:
    """Resolve report source records to ACNC records only on an ABN disclosed in text."""
    acnc_by_abn = {
        next(item.value for item in record.external_identifiers if item.scheme == "abn"): record
        for record in parse_acnc_register_csv(acnc_csv_path)
        if any(item.scheme == "abn" for item in record.external_identifiers)
    }
    inventory_by_hash = {}
    if source_inventory_path:
        inventory = json.loads(source_inventory_path.read_text(encoding="utf-8"))
        inventory_by_hash = {
            entry["sha256"]: entry["external_identifier"]["value"]
            for entry in inventory.get("sources", [])
            if entry.get("external_identifier", {}).get("scheme") == "abn"
        }
    rows = []
    for path in extract_paths:
        extract = json.loads(path.read_text(encoding="utf-8"))
        text = "\n".join(page["text"] for page in extract["pages"])
        abns = sorted(
            {
                re.sub(r"\D", "", value)
                for value in re.findall(r"\bABN\s*[:#]?\s*([0-9 ][0-9 ]{9,})", text, flags=re.I)
                if len(re.sub(r"\D", "", value)) == 11
            }
        )
        inventory_abn = inventory_by_hash.get(extract["source_sha256"])
        resolved_abns = sorted(set(abns + ([inventory_abn] if inventory_abn else [])))
        matches = [acnc_by_abn[abn] for abn in resolved_abns if abn in acnc_by_abn]
        has_report_abn = bool([abn for abn in abns if abn in acnc_by_abn])
        has_inventory_abn = inventory_abn in acnc_by_abn
        rows.append(
            {
                "source_record_id": f"src:annual-report:{extract['source_sha256']}",
                "extract_file": path.name,
                "resolution_status": "resolved" if len(matches) == 1 else "unresolved",
                "resolution_basis": (
                    "ABN disclosed in report text and matched to ACNC Register"
                    if has_report_abn and len(matches) == 1
                    else "ABN recorded in curated source inventory and matched to ACNC Register"
                    if has_inventory_abn and len(matches) == 1
                    else "no uniquely matchable ABN in report text or source inventory"
                ),
                "confidence": "high" if len(matches) == 1 else "low",
                "supporting_signals": [
                    f"ABN:{matches[0].external_identifiers[-1].value}",
                    "report text" if has_report_abn else "curated source inventory",
                ] if len(matches) == 1 else [],
                "conflicting_signals": [],
                "review_status": "not_required" if len(matches) == 1 else "pending",
                "matched_acnc_records": [
                    {
                        "source_record_id": record.source_record_id,
                        "legal_name": record.legal_name,
                        "display_name": record.display_name,
                    }
                    for record in matches
                ],
            }
        )
    return {"rows": rows}

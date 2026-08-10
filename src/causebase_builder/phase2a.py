"""Bounded, cache-aware Phase 2A enrichment orchestration.

Everything under the supplied archive directory is private working evidence.
Only callers that explicitly render a publication may project public-safe card
fields from it.
"""

from __future__ import annotations

import json
from datetime import datetime
from datetime import date
from pathlib import Path
from typing import Any

from .models import CauseBaseCard, Classification, CoverageObservation, SynthesisMetadata
from .pipeline import build_card
from .synthesis import SYNTHESIS_PROMPT_VERSION, evidence_hash, synthesize_evidence
from .sources.ais import parse_ais_financial_csv


def load_taxonomy(path: Path) -> dict[str, Any]:
    taxonomy = json.loads(path.read_text(encoding="utf-8"))
    required = {"taxonomy_id", "version", "terms"}
    missing = required - taxonomy.keys()
    if missing:
        raise ValueError(f"taxonomy missing {sorted(missing)}")
    ids = [term["term_id"] for term in taxonomy["terms"]]
    if len(ids) != len(set(ids)):
        raise ValueError("taxonomy has duplicate term IDs")
    return taxonomy


def load_governed_entities(path: Path) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    for file in sorted(path.glob("*.json")):
        payload = json.loads(file.read_text(encoding="utf-8"))
        entities.extend(payload.get("entities", []))
    return entities


def materialise_acnc_gate2_entities(
    cohort: dict[str, Any], registry_payload: dict[str, Any], ais_csv: Path, web_extract_dir: Path | None = None,
    report_extract_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Create evidence-grounded source inputs for promoted ACNC subjects.

    This uses current structured records only. Report and web coverage remain
    explicit until separately acquired; no placeholder prose is introduced.
    """
    promoted = {
        subject["promotion"]["source_record_ids"][0]: subject
        for subject in registry_payload["subjects"]
        if subject.get("promotion", {}).get("promotion_method") == "automated_authoritative_source"
    }
    ais_by_abn = {record.abn: record for record in parse_ais_financial_csv(ais_csv)}
    entities: list[dict[str, Any]] = []
    for candidate in cohort["selected_candidates"]:
        subject = promoted.get(candidate["source_record_id"])
        if not subject:
            continue
        abn = candidate["abn"]
        acnc_evidence = f"ev:acnc:{abn}"
        ais = ais_by_abn.get(abn)
        evidence = [{
            "evidence_id": acnc_evidence, "source_type": "regulatory",
            "title": "ACNC Register extract", "publisher": "Australian Charities and Not-for-profits Commission",
            "observed_at": "2026-08-10",
        }]
        web_extract = None
        if web_extract_dir:
            web_path = web_extract_dir / f"{abn}-2026-08-10.json"
            if web_path.exists():
                web_extract = json.loads(web_path.read_text(encoding="utf-8"))
        report_extracts: list[dict[str, Any]] = []
        if report_extract_dir:
            for report_path in sorted(report_extract_dir.glob(f"{abn}-*.json")):
                report = json.loads(report_path.read_text(encoding="utf-8"))
                if report.get("status") == "observed" and report.get("pages"):
                    report_extracts.append(report)
        coverage = [
            {"capability": "regulatory", "status": "observed", "evidence_ids": [acnc_evidence], "observed_at": "2026-08-10"},
            {"capability": "annual_report", "status": "observed" if report_extracts else "not_yet_processed", "observed_at": "2026-08-10"},
            {"capability": "website", "status": web_extract.get("status") if web_extract else ("not_yet_processed" if candidate.get("website") else "not_available_from_source"), "observed_at": "2026-08-10"},
            {"capability": "fundraising_expenditure", "status": "not_yet_processed", "observed_at": "2026-08-10"},
        ]
        financials: dict[str, Any] | None = None
        if web_extract and web_extract.get("status") == "observed":
            web_evidence = f"ev:web:{abn}:2026-08-10"
            evidence.append({
                "evidence_id": web_evidence, "source_type": "organisation_self_report", "title": "Organisation website homepage",
                "publisher": candidate["legal_name"], "url": web_extract.get("source_url"), "observed_at": "2026-08-10",
            })
            coverage[2] = {"capability": "website", "status": "observed", "evidence_ids": [web_evidence], "observed_at": "2026-08-10"}
        report_evidence_ids = []
        for report in report_extracts:
            report_evidence = f"ev:report:{abn}:{report['source_sha256'][:12]}"
            report_evidence_ids.append(report_evidence)
            evidence.append({
                "evidence_id": report_evidence, "source_type": "organisation_self_report", "title": "Organisation annual or financial report",
                "publisher": candidate["legal_name"], "url": report.get("source_url"), "observed_at": report.get("retrieved_at", "2026-08-10")[:10],
            })
        if report_evidence_ids:
            coverage[1] = {"capability": "annual_report", "status": "observed", "evidence_ids": report_evidence_ids, "observed_at": "2026-08-10"}
        if ais:
            ais_evidence = f"ev:ais:{abn}:2023"
            evidence.append({
                "evidence_id": ais_evidence, "source_type": "regulatory", "title": "ACNC AIS 2023 extract",
                "publisher": "Australian Charities and Not-for-profits Commission", "observed_at": "2026-08-10",
                "reporting_period": ais.reporting_period,
            })
            def parsed(value: str | None):
                if not value:
                    return None
                return datetime.strptime(value, "%d/%m/%Y").date().isoformat()
            start, end = parsed(ais.financial_report_from), parsed(ais.financial_report_to)
            length = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).days + 1 if start and end else None
            financials = {
                "financial_record_id": f"fr:ais:{subject['causebase_id']}:2023",
                "period": {"period_start": start, "period_end": end, "period_length_days": length, "label": ais.reporting_period, "is_transitional_or_nonstandard": bool(length and not 350 <= length <= 380)},
                "reporting_scope": "subject", "reporting_subject_causebase_id": subject["causebase_id"],
                "covered_subjects": [subject["causebase_id"]], "consolidated": ais.consolidated,
                "attribution_method": "direct_subject_report", "evidence_ids": [ais_evidence],
                "revenue": ais.revenue.model_dump(mode="json") if ais.revenue else None,
                "total_expenses": ais.total_expenses.model_dump(mode="json") if ais.total_expenses else None,
            }
            coverage.append({"capability": "financials", "status": "observed", "evidence_ids": [ais_evidence], "observed_at": "2026-08-10"})
        else:
            coverage.append({"capability": "financials", "status": "not_found_in_source", "observed_at": "2026-08-10"})
        strata = candidate["strata"]
        entities.append({
            "causebase_id": subject["causebase_id"], "subject_kind": "unknown",
            "external_identifiers": [{"scheme": "abn", "value": abn, "source_evidence_id": acnc_evidence}],
            "registrations": [{"regulator": "ACNC", "status": "registered", "evidence_ids": [acnc_evidence]}],
            "source_resolutions": [{"source_record_id": candidate["source_record_id"], "resolution_status": "resolved", "resolution_basis": "automated authoritative ACNC promotion under acnc-authoritative-v1", "confidence": "high", "supporting_signals": [f"ABN:{abn}", "ACNC Register"], "review_status": "not_required"}],
            "legal_name": candidate["legal_name"], "display_name": candidate["display_name"], "entity_status": "registered",
            "enrichment_level": "thin", "website": candidate.get("website"), "geography": [strata["state"]] if strata["state"] != "unknown_state" else [],
            "activities": [], "beneficiaries": [], "participation_modes": [],
            "classifications": [
                {"taxonomy_id": "acnc-register", "taxonomy_version": "2026-08-10", "term_id": f"purpose.{strata['purpose']}", "term_label": strata["purpose"].replace("_", " "), "assignment_method": "source_native", "confidence": "high", "evidence_ids": [acnc_evidence]},
                {"taxonomy_id": "acnc-register", "taxonomy_version": "2026-08-10", "term_id": f"beneficiary.{strata['beneficiary']}", "term_label": strata["beneficiary"].replace("_", " "), "assignment_method": "source_native", "confidence": "high", "evidence_ids": [acnc_evidence]},
            ],
            "coverage": coverage, "financials": financials or {}, "fundraising": {}, "evidence": evidence,
        })
    return entities


def _abn(entity: dict[str, Any]) -> str | None:
    return next((item["value"] for item in entity.get("external_identifiers", []) if item.get("scheme") == "abn"), None)


def _report_and_web_excerpts(entity: dict[str, Any], archive_root: Path) -> list[dict[str, Any]]:
    """Select bounded private excerpts and retain source/page provenance."""
    abn = _abn(entity)
    if not abn:
        return []
    processed = archive_root / "processed" / "reality-spike" / "2026-08-10"
    excerpts: list[dict[str, Any]] = []
    report_files = sorted((processed / "report-extracts").glob(f"{abn}-*.json"))
    # Prefer non-truncated extracts where both variants exist; avoid duplicate pages.
    selected_report = next((item for item in report_files if item.stem.endswith("-full")), report_files[0] if report_files else None)
    if selected_report:
        extracted = json.loads(selected_report.read_text(encoding="utf-8"))
        remaining = 14_000
        for page in extracted.get("pages", []):
            text = (page.get("text") or "").strip()
            if not text or remaining <= 0:
                continue
            excerpt = text[:remaining]
            excerpts.append({"kind": "annual_or_financial_report", "page": page.get("page"), "text": excerpt})
            remaining -= len(excerpt)
    phase2_reports = archive_root / "processed" / "phase2a" / "2026-08-10" / "report-extracts"
    for report_path in sorted(phase2_reports.glob(f"{abn}-*.json")) if phase2_reports.exists() else []:
        extracted = json.loads(report_path.read_text(encoding="utf-8"))
        remaining = 14_000
        for page in extracted.get("pages", []):
            text = (page.get("text") or "").strip()
            if not text or remaining <= 0:
                continue
            excerpt = text[:remaining]
            excerpts.append({"kind": "annual_or_financial_report", "page": page.get("page"), "text": excerpt})
            remaining -= len(excerpt)
    web_files = sorted((processed / "web-extracts").glob(f"{abn}-*.json"))
    phase2_web = archive_root / "processed" / "phase2a" / "2026-08-10" / "web-extracts"
    if phase2_web.exists():
        web_files.extend(sorted(phase2_web.glob(f"{abn}-*.json")))
    for file in web_files[:2]:
        payload = json.loads(file.read_text(encoding="utf-8"))
        text = (payload.get("readable_text") or "").strip()
        if text:
            excerpts.append({"kind": "website_snapshot", "text": text[:8_000]})
    return excerpts


def make_evidence_pack(entity: dict[str, Any], archive_root: Path) -> dict[str, Any]:
    """Create the bounded selected evidence consumed by synthesis."""
    return {
        "subject": {
            "causebase_id": entity["causebase_id"],
            "legal_name": entity["legal_name"],
            "display_name": entity["display_name"],
            "website": entity.get("website"),
            "structured_geography": entity.get("geography", []),
            "structured_activities": entity.get("activities", []),
            "structured_beneficiaries": entity.get("beneficiaries", []),
            "structured_participation": entity.get("participation_modes", []),
            "self_description": entity.get("organisation_self_description"),
        },
        "source_index": [
            {
                "evidence_id": item["evidence_id"], "source_type": item["source_type"],
                "title": item["title"], "url": item.get("url"), "observed_at": item["observed_at"],
                "page": item.get("page"), "reporting_period": item.get("reporting_period"),
            }
            for item in entity.get("evidence", [])
        ],
        "financial_records": entity.get("financial_records") or [entity.get("financials", {})],
        "selected_private_excerpts": _report_and_web_excerpts(entity, archive_root),
        "known_coverage": entity.get("coverage", []),
    }


def _cache_path(cache_root: Path, *, pack: dict[str, Any], taxonomy: dict[str, Any], model: str) -> Path:
    key = evidence_hash({"pack": pack, "taxonomy_version": taxonomy["version"], "model": model, "prompt_version": SYNTHESIS_PROMPT_VERSION})
    return cache_root / f"{key}.json"


def enrich_governed_entity(
    *, entity: dict[str, Any], archive_root: Path, cache_root: Path, taxonomy: dict[str, Any],
    dataset_version: str, model: str = "gpt-5-mini",
) -> tuple[CauseBaseCard, dict[str, Any]]:
    """Enrich one already-governed subject, reusing a private cache by content hash."""
    pack = make_evidence_pack(entity, archive_root)
    cache_file = _cache_path(cache_root, pack=pack, taxonomy=taxonomy, model=model)
    cache_root.mkdir(parents=True, exist_ok=True)
    cache_hit = cache_file.exists()
    if cache_hit:
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        output, provenance = cached["output"], cached["provenance"]
    else:
        terms = [{"term_id": term["term_id"], "label": term["label"]} for term in taxonomy["terms"]]
        output, provenance = synthesize_evidence(evidence_pack=pack, taxonomy_terms=terms, model=model)
        cache_file.write_text(json.dumps({"output": output, "provenance": provenance}, indent=2), encoding="utf-8")

    card = build_card(entity, dataset_version)
    card.causebase_summary = output["summary"].strip()
    card.activities = output["activities"]
    card.beneficiaries = output["beneficiaries"]
    card.geography = output["geography"] or card.geography
    card.participation_modes = output["participation_modes"]
    valid_terms = {term["term_id"]: term for term in taxonomy["terms"]}
    grounding_ids = [item["evidence_id"] for item in entity.get("evidence", [])]
    external_classifications = list(card.classifications)
    card.classifications = external_classifications + [
        Classification(
            taxonomy_id=taxonomy["taxonomy_id"], taxonomy_version=taxonomy["version"],
            term_id=term_id, term_label=valid_terms[term_id]["label"],
            assignment_method="llm_classification", confidence="medium", evidence_ids=grounding_ids,
        )
        for term_id in output["taxonomy_term_ids"] if term_id in valid_terms
    ]
    # Phase 2A does not permit the old synthetic fallback prior. Preserve a
    # transparent coverage state instead of presenting a made-up scalar.
    if card.fundraising_expenditure and card.fundraising_expenditure.method == "fallback_prior":
        card.fundraising_expenditure = None
        card.coverage.append(CoverageObservation(
            capability="fundraising_expenditure", status="not_available_from_source",
            observed_at=date.today(), freshness_note="No direct or defensible derived fundraising expenditure was found in selected Phase 2A evidence.",
        ))
    card.enrichment_level = "enriched"
    card.synthesis = SynthesisMetadata.model_validate(provenance)
    card = CauseBaseCard.model_validate(card.model_dump(mode="json"))
    return card, {
        "causebase_id": card.causebase_id,
        "cache_hit": cache_hit,
        "evidence_input_hash": card.synthesis.evidence_input_hash,
        "input_tokens": card.synthesis.input_tokens,
        "output_tokens": card.synthesis.output_tokens,
        "estimated_cost_usd": str(card.synthesis.estimated_cost_usd) if card.synthesis.estimated_cost_usd is not None else None,
    }

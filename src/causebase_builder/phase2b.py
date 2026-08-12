"""Phase 2B release projection for an existing validated enriched corpus.

The projection is deliberately append-only: it reads a historical release,
adds new public contract surfaces, and writes a separately versioned release.
It never edits the input directory or regenerates expensive derivatives.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .models import CauseBaseCard, DerivativeAssessment, FundingSourceObservation, NavigationGeography, SourceNativeRecord, SynthesisMetadata
from .render import file_sha256, render_publication
from .phase2a import _cache_path, load_taxonomy, make_evidence_pack
from .synthesis import SYNTHESIS_PROMPT_VERSION, synthesize_evidence


PHASE2B_GENERATOR_VERSION = "0.3.0-rc2"
EDITORIAL_POLICY_VERSION = "0.3-rc2"


_STATE_CODES = {
    "victoria": "AU-VIC", "new south wales": "AU-NSW", "queensland": "AU-QLD",
    "south australia": "AU-SA", "western australia": "AU-WA", "tasmania": "AU-TAS",
    "australian capital territory": "AU-ACT", "northern territory": "AU-NT",
}


def _navigation_geography(card: CauseBaseCard) -> list[NavigationGeography]:
    text = " ".join(card.geography).lower()
    evidence_ids = [item.evidence_id for item in card.evidence if item.evidence_id.startswith(("ev:acnc:", "ev:web:"))]
    values: list[NavigationGeography] = []
    for label, code in _STATE_CODES.items():
        if label in text:
            values.append(NavigationGeography(level="state_territory", code=code, label=label.title(), evidence_ids=evidence_ids[:1]))
    # ACNC registration establishes Australia as the registry jurisdiction; do
    # not infer national operations from it.
    if any(item.scheme.lower() == "abn" for item in card.external_identifiers):
        values.insert(0, NavigationGeography(level="country", code="AU", label="Australia", evidence_ids=evidence_ids[:1]))
    return values


def source_inventory() -> dict:
    return {
        "inventory_version": "phase2b-0.1",
        "scope": "Current 120-subject human-test corpus; the source architecture supports broader public coverage.",
        "source_families": [
            {
                "source_name": "ACNC Charity Register", "publisher": "Australian Charities and Not-for-profits Commission",
                "source_url": "https://www.acnc.gov.au/charity/about-charity-register/download-charity-register-data",
                "licence_or_attribution": "Government source; retain ACNC attribution. Verify dataset-specific terms at each refresh.",
                "refresh_cadence": "Register dataset regularly updated", "historical_coverage": "Current register projection; source history retained when acquired.",
                "identity_keys": ["ABN", "ACNC source-record ID"], "source_field_count": "variable dataset schema",
                "currently_preserved": ["identity", "legal name", "registration status", "source-native classifications"],
                "currently_canonicalised": ["registration", "external identifiers", "classifications"],
                "currently_discarded": [], "not_yet_processed": ["full public profile field surface", "people records"],
                "limitations": "Withheld information is not present in public datasets.",
            },
            {
                "source_name": "ACNC Annual Information Statement datasets", "publisher": "Australian Charities and Not-for-profits Commission",
                "source_url": "https://www.acnc.gov.au/charity/about-charity-register/download-charity-register-data",
                "licence_or_attribution": "Government source; retain ACNC attribution. Verify dataset-specific terms at each refresh.",
                "refresh_cadence": "Annual datasets updated weekly", "historical_coverage": "Acquired annual observations are append-only.",
                "identity_keys": ["ABN", "reporting period", "AIS source-record ID"], "source_field_count": "variable dataset schema",
                "currently_preserved": ["financial values", "period", "reporting scope", "selected source-native fields"],
                "currently_canonicalised": ["financial records", "financial metrics", "government grants", "donations"],
                "currently_discarded": [], "not_yet_processed": ["full activity/program and beneficiary history for all years"],
                "limitations": "Source disclosures and reporting requirements vary by charity size and exemptions.",
            },
            {
                "source_name": "ABR / ATO ABN Lookup bulk extract and DGR material", "publisher": "Australian Business Register / Australian Taxation Office",
                "source_url": "https://abr.business.gov.au/Tools/BulkExtract",
                "licence_or_attribution": "ABR bulk extract terms apply; existing DGR ingest records its source metadata.",
                "refresh_cadence": "Weekly bulk extract", "historical_coverage": "Dated DGR observations retained when acquired.",
                "identity_keys": ["ABN"], "source_field_count": "bulk extract schema",
                "currently_preserved": ["dated DGR status in private backbone"],
                "currently_canonicalised": ["external tax status when resolved"], "currently_discarded": [],
                "not_yet_processed": ["expanded ABR entity and business-name history for the 120 cards"],
                "limitations": "DGR presence is source-date-specific; absence is not a general negative claim.",
            },
            {
                "source_name": "ASIC public information", "publisher": "Australian Securities and Investments Commission",
                "source_url": "https://asic.gov.au/online-services/search-asic-registers/",
                "licence_or_attribution": "Not integrated pending record-level access, cost and terms review.",
                "refresh_cadence": "Not assessed", "historical_coverage": "Not assessed", "identity_keys": ["ACN", "ARBN"],
                "source_field_count": "Not assessed", "currently_preserved": [], "currently_canonicalised": [], "currently_discarded": [],
                "not_yet_processed": ["ASIC integration"],
                "limitations": "Some records/documents may be fee-based or subject to access terms; CauseBase does not scrape around payment or access controls.",
            },
        ],
        "gap_report": [
            "The initial 120-card release has only the source observations acquired for Phase 2A; it is not a complete regulator mirror.",
            "Full ACNC programs, beneficiaries, locations and status history require a new acquired source observation before publication.",
            "ASIC integration remains a product/legal/economic assessment, not a scraping task.",
        ],
    }


def _native_records(card: CauseBaseCard, now: datetime) -> list[SourceNativeRecord]:
    records: list[SourceNativeRecord] = []
    abn = next((item.value for item in card.external_identifiers if item.scheme.lower() == "abn"), None)
    acnc_evidence = next((item.evidence_id for item in card.evidence if item.evidence_id.startswith("ev:acnc:")), None)
    source_resolution = next((item.source_record_id for item in card.source_resolutions if "acnc" in item.source_record_id), None)
    if acnc_evidence:
        records.append(SourceNativeRecord(
            source_record_id=source_resolution or f"src:acnc-register:{abn or card.causebase_id}",
            source_family="acnc-register", dataset_version="2026-08-10", source_url=f"https://www.acnc.gov.au/charity/charities?search={abn}" if abn else None,
            retrieved_at=now, observed_at=next(item.observed_at for item in card.evidence if item.evidence_id == acnc_evidence),
            source_fields={"ABN": abn, "Legal Name": card.legal_name, "Registration Status": card.entity_status,
                           "ACNC classifications": "; ".join(c.term_label for c in card.classifications if c.taxonomy_id == "acnc-register") or None,
                           "Website": card.website,
                           "ACNC registration ID": next((r.registration_id for r in card.registrations if r.regulator == "ACNC"), None),
                           "Public source field coverage": "Fields acquired in the Phase 2A register observation are preserved here; fields absent from that acquired observation are explicitly not_yet_processed rather than inferred."},
            canonical_field_mappings={"ABN": "external_identifiers", "Legal Name": "legal_name", "Registration Status": "registrations"},
            evidence_ids=[acnc_evidence],
        ))
    for financial in card.financial_records:
        evidence_ids = list(financial.evidence_ids)
        observed = next((e.observed_at for e in card.evidence if e.evidence_id in evidence_ids), None)
        fields = {"Reporting period": financial.period.label, "Reporting scope": financial.reporting_scope,
                  "Consolidated": financial.consolidated}
        for field_name, source_label in (("revenue", "Revenue"), ("donations", "Donations and bequests"),
                                         ("government_grants", "Government grants"), ("total_expenses", "Total expenses"),
                                         ("assets", "Assets"), ("liabilities", "Liabilities")):
            value = getattr(financial, field_name)
            fields[source_label] = str(value.source_amount) if value else None
        records.append(SourceNativeRecord(
            source_record_id=f"src:acnc-ais:{financial.financial_record_id}", source_family="acnc-ais",
            dataset_version="2026-08-10", retrieved_at=now, observed_at=observed,
            effective_from=financial.period.period_start, effective_to=financial.period.period_end,
            source_fields=fields,
            canonical_field_mappings={"Revenue": "financial_records[].revenue", "Total expenses": "financial_records[].total_expenses"},
            evidence_ids=evidence_ids,
        ))
    return records


def _funding(card: CauseBaseCard) -> list[FundingSourceObservation]:
    observations: list[FundingSourceObservation] = []
    for record in card.financial_records:
        for name, source_type, label in (
            ("government_grants", "government_grants_or_contracts", "Government grants"),
            ("donations", "individual_donations", "Donations and bequests (source category)"),
        ):
            amount = getattr(record, name)
            if amount is not None:
                observations.append(FundingSourceObservation(
                    source_type=source_type, source_label=label, period_label=record.period.label,
                    amount=amount, reporting_scope=record.reporting_scope, evidence_ids=record.evidence_ids,
                ))
    return observations


def project_phase2b(input_dir: Path, output_dir: Path, dataset_version: str, *, archive_root: Path | None = None, cache_root: Path | None = None, model: str = "gpt-5-mini") -> dict:
    raw = json.loads((input_dir / "causebase.json").read_text(encoding="utf-8"))
    source_manifest = json.loads((input_dir / "manifest.json").read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    cards: list[CauseBaseCard] = []
    taxonomy = json.loads((input_dir / "taxonomy" / "causebase-v0.json").read_text(encoding="utf-8"))
    migration = {"reason": "Editorial policy, synthesis prompt and summary output contract changed for Phase 2B RC2.", "model": model, "calls": 0, "input_tokens": 0, "output_tokens": 0, "estimated_cost_usd": "0"}
    for row in raw["entities"]:
        card = CauseBaseCard.model_validate(row)
        card.dataset_version = dataset_version
        card.card_schema_version = "0.3"
        card.editorial_policy_version = EDITORIAL_POLICY_VERSION
        card.generator_version = PHASE2B_GENERATOR_VERSION
        card.built_at = now
        card.source_native_records = _native_records(card, now)
        card.funding_sources = _funding(card)
        card.navigation_geography = _navigation_geography(card)
        # The deliberate RC2 editorial migration invalidates each old summary,
        # even where selected evidence is byte-identical.
        if archive_root is None or cache_root is None:
            raise ValueError("RC2 summary migration requires private archive_root and cache_root")
        pack = make_evidence_pack(row, archive_root)
        cache_file = _cache_path(cache_root, pack=pack, taxonomy=taxonomy, model=model)
        cache_root.mkdir(parents=True, exist_ok=True)
        if cache_file.exists():
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            output, provenance = cached["output"], cached["provenance"]
        else:
            terms = [{"term_id": term["term_id"], "label": term["label"]} for term in taxonomy["terms"]]
            output, provenance = synthesize_evidence(evidence_pack=pack, taxonomy_terms=terms, model=model)
            cache_file.write_text(json.dumps({"output": output, "provenance": provenance}, indent=2), encoding="utf-8")
        # Record the entire deliberate migration, including cache hits on a
        # later rendering attempt. The private cache is the authoritative
        # operational ledger; only aggregate telemetry is released.
        if cache_file.exists():
            from decimal import Decimal
            migration["calls"] += 1
            migration["input_tokens"] += provenance.get("input_tokens") or 0
            migration["output_tokens"] += provenance.get("output_tokens") or 0
            migration["estimated_cost_usd"] = str(Decimal(migration["estimated_cost_usd"]) + Decimal(provenance.get("estimated_cost_usd") or "0"))
        card.causebase_summary = output["summary"].strip()
        known_evidence_ids = {item.evidence_id for item in card.evidence}
        card.summary_evidence_ids = [item for item in output.get("summary_evidence_ids", []) if item in known_evidence_ids] or [item.evidence_id for item in card.evidence[:1]]
        card.synthesis = SynthesisMetadata.model_validate({key: provenance[key] for key in ("model_id", "prompt_version", "parameters", "evidence_input_hash", "generated_at", "editorial_policy_version") if key in provenance})
        input_hash = card.synthesis.evidence_input_hash if card.synthesis else "not_available"
        generated_at = card.synthesis.generated_at if card.synthesis else None
        card.derivative_assessments = [
            DerivativeAssessment(derivative="summary", generated_at=card.synthesis.generated_at if card.synthesis else generated_at, evidence_through=None, last_assessed_at=now,
                                 assessment_method="phase2b-rc2-editorial-migration", input_hash=card.synthesis.evidence_input_hash if card.synthesis else input_hash, disposition="refreshed",
                                 reason="Refreshed because the RC2 prompt, editorial policy and summary citation contract supersede h1."),
            DerivativeAssessment(derivative="taxonomy", generated_at=generated_at, evidence_through=None, last_assessed_at=now,
                                 assessment_method="phase2b-deterministic-v1", input_hash=input_hash, disposition="reused",
                                 reason="No new supported canonical classification facts."),
            DerivativeAssessment(derivative="fundraising", generated_at=None, evidence_through=None, last_assessed_at=now,
                                 assessment_method="phase2b-deterministic-v1", input_hash=input_hash, disposition="reused",
                                 reason="No new fundraising-method evidence; funding observations are direct AIS projections."),
            DerivativeAssessment(derivative="embedding", generated_at=card.embedding.generated_at if card.embedding else None, evidence_through=None, last_assessed_at=now,
                                 assessment_method="phase2b-deterministic-v1", input_hash=card.embedding.source_text_hash if card.embedding else input_hash,
                                 disposition="reused", reason="Semantic source text unchanged."),
            DerivativeAssessment(derivative="similarities", generated_at=card.embedding.generated_at if card.embedding else None, evidence_through=None, last_assessed_at=now,
                                 assessment_method="phase2b-deterministic-v1", input_hash=card.embedding.source_text_hash if card.embedding else input_hash,
                                 disposition="reused", reason="Embedding reused; semantic neighbours retained."),
        ]
        cards.append(card)
    vectors = {row["causebase_id"]: row["vector"] for row in json.loads((input_dir / "embeddings.json").read_text(encoding="utf-8"))}
    similarities = json.loads((input_dir / "similarities.json").read_text(encoding="utf-8"))
    for row in similarities:
        row["dataset_version"] = dataset_version
    history = {"releases": [
        {"dataset_version": source_manifest["dataset_version"], "status": "historical", "manifest_sha256": file_sha256(input_dir / "manifest.json"), "immutable": True},
        {"dataset_version": dataset_version, "status": "candidate", "derived_from": source_manifest["dataset_version"], "immutable": False},
    ]}
    inventory = source_inventory()
    inventory["migration"] = migration
    inventory["gap_report"] = [
        "All regulator fields present in the acquired Phase 2A ACNC/AIS observations are exposed canonically or in source-native sidecars.",
        "A field not present in those acquired observations is explicitly represented as not_yet_processed; this candidate does not claim to mirror unacquired ACNC profile surfaces.",
        "ASIC remains outside the accepted access/cost/terms boundary.",
    ]
    return render_publication(cards, vectors, similarities, output_dir, taxonomy=taxonomy,
        agent_guide=(input_dir / "agent-guide.md").read_text(encoding="utf-8"), source_inventory=inventory, release_history=history)

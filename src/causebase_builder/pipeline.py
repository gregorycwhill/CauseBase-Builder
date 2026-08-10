from __future__ import annotations

import json
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path

from .fundraising import estimate_fundraising
from .models import (
    CauseBaseCard,
    Classification,
    CoverageObservation,
    EvidenceRef,
    ExternalIdentifier,
    Financials,
    FinancialMetricObservation,
    FinancialMetricSet,
    Opportunity,
    SubjectRelationship,
    Registration,
    SourceResolution,
    TaxStatus,
)
from .semantic import attach_demo_embedding, build_similarity_rows
from .synthesis import deterministic_fixture_summary


def load_fixture_entities(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["entities"]


def build_card(source: dict, dataset_version: str) -> CauseBaseCard:
    evidence = [EvidenceRef.model_validate(e) for e in source["evidence"]]
    classifications = [
        Classification.model_validate(c) for c in source.get("classifications", [])
    ]
    opportunities = [
        Opportunity.model_validate(o) for o in source.get("opportunities", [])
    ]
    external_identifiers = [
        ExternalIdentifier.model_validate(identifier)
        for identifier in source.get("external_identifiers", [])
    ]
    relationships = [
        SubjectRelationship.model_validate(relationship)
        for relationship in source.get("relationships", [])
    ]

    coverage_source = source.get("coverage", [])
    if isinstance(coverage_source, dict):
        # Compatibility only for the synthetic fixture input. Publication output always
        # uses explicit observations, never a capability boolean map.
        coverage_source = [
            {
                "capability": capability,
                "status": "observed" if value is True else "not_yet_processed",
            }
            for capability, value in coverage_source.items()
            if isinstance(value, bool)
        ]
    financials_source = dict(source.get("financials", {}))
    if financials_source and isinstance(financials_source.get("period"), str):
        financials_source["period"] = {"label": financials_source["period"]}
    if financials_source:
        financials_source.setdefault(
        "financial_record_id", f"fr:{source['causebase_id']}:fixture"
        )
        financials_source.setdefault("reporting_scope", "subject")
        financials_source.setdefault("reporting_subject_causebase_id", source["causebase_id"])
        financials_source.setdefault("covered_subjects", [source["causebase_id"]])
        financials_source.setdefault("consolidated", "false")
        financials_source.setdefault("attribution_method", "direct_subject_report")
    for field in (
        "revenue", "donations", "government_grants", "employee_costs",
        "total_expenses", "assets", "liabilities",
    ):
        value = financials_source.get(field)
        if value is not None and not isinstance(value, dict):
            amount = Decimal(str(value))
            financials_source[field] = {
                "source_amount": amount,
                "source_currency": "AUD",
                "source_unit_scale": 1,
                "normalised_amount": amount,
                "normalised_currency": "AUD",
                "source_raw_value": str(value),
            }

    financial_record = Financials.model_validate(financials_source) if financials_source else None
    metric_names = (
        "revenue", "donations", "government_grants", "employee_costs",
        "total_expenses", "assets", "liabilities",
    )
    financial_metrics = [
        FinancialMetricSet(
            metric=metric,
            observations=[
                FinancialMetricObservation(
                    financial_record_id=financial_record.financial_record_id,
                    amount=getattr(financial_record, metric),
                    evidence_ids=financial_record.evidence_ids,
                )
            ],
            reconciliation_status="single_observation",
        )
        for metric in metric_names
        if financial_record is not None and getattr(financial_record, metric) is not None
    ]
    financial_records = [financial_record] if financial_record is not None else []
    if source.get("financial_records"):
        financial_records = [Financials.model_validate(item) for item in source["financial_records"]]
        financial_metrics = [
            FinancialMetricSet.model_validate(item)
            for item in source.get("financial_metrics", [])
        ]
    fundraising_source = (source.get("financial_records") or [financials_source])[0] if financial_records else {}

    return CauseBaseCard(
        causebase_id=source["causebase_id"],
        subject_kind=source.get("subject_kind", source.get("subject_type", "organisation")),
        external_identifiers=external_identifiers,
        relationships=relationships,
        registrations=[Registration.model_validate(item) for item in source.get("registrations", [])],
        tax_statuses=[TaxStatus.model_validate(item) for item in source.get("tax_statuses", [])],
        source_resolutions=[SourceResolution.model_validate(item) for item in source.get("source_resolutions", [])],
        legal_name=source["legal_name"],
        display_name=source["display_name"],
        entity_status=source.get("entity_status", "registered"),
        coverage=[CoverageObservation.model_validate(item) for item in coverage_source],
        enrichment_level=source.get("enrichment_level"),
        website=source.get("website"),
        geography=source.get("geography", []),
        causebase_summary=deterministic_fixture_summary(source),
        organisation_self_description=source.get("organisation_self_description"),
        activities=source.get("activities", []),
        beneficiaries=source.get("beneficiaries", []),
        participation_modes=source.get("participation_modes", []),
        opportunities=opportunities,
        financial_records=financial_records,
        financial_metrics=financial_metrics,
        fundraising_expenditure=(
            estimate_fundraising({**source, "financials": fundraising_source})
            if financial_records and fundraising_source.get("total_expenses") is not None
            else None
        ),
        classifications=classifications,
        evidence=evidence,
        dataset_version=dataset_version,
        built_at=datetime.now(timezone.utc),
    )


def build_fixture_corpus(source_path: Path, dataset_version: str):
    sources = load_fixture_entities(source_path)
    cards = [build_card(s, dataset_version) for s in sources]

    vectors: dict[str, list[float]] = {}
    embedded_cards = []
    for card in cards:
        card, vector = attach_demo_embedding(card)
        vectors[card.causebase_id] = vector
        embedded_cards.append(card)

    similarities = build_similarity_rows(embedded_cards, vectors)
    return embedded_cards, vectors, similarities

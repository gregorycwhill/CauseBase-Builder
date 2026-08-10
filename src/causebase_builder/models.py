from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator


SourceType = Literal[
    "regulatory",
    "organisation_self_report",
    "independent_reference",
    "community_contribution",
]

SubjectKind = Literal[
    "organisation",
    "organisation_group",
    "legal_entity",
    "fund",
    "organisational_unit",
    "program",
]

RelationshipType = Literal[
    "registered_as",
    "operates_as",
    "part_of",
    "branch_of",
    "program_of",
    "auspiced_by",
    "successor_to",
]

ResolutionStatus = Literal["resolved", "candidate", "ambiguous", "unresolved"]
ResolutionConfidence = Literal["high", "medium", "low"]
CoverageStatus = Literal[
    "observed",
    "not_found_in_source",
    "not_available_from_source",
    "not_applicable",
    "retrieval_failed",
    "not_yet_processed",
    "stale",
    "unknown",
]

DerivationMethod = Literal[
    "direct_extract",
    "deterministic_derivation",
    "heuristic_estimate",
    "llm_interpretation",
    "peer_imputation",
    "fallback_prior",
]


class EvidenceRef(BaseModel):
    evidence_id: str
    source_type: SourceType
    title: str
    publisher: str | None = None
    url: str | None = None
    observed_at: date
    reporting_period: str | None = None
    page: int | None = None
    section: str | None = None
    content_hash: str | None = None


class ExternalIdentifier(BaseModel):
    """An identifier issued by an external system, never the CauseBase primary key."""

    scheme: str
    value: str
    source_evidence_id: str | None = None


class Registration(BaseModel):
    regulator: str
    registration_id: str | None = None
    status: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class TaxStatus(BaseModel):
    scheme: str
    status: str | None = None
    detail: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class SourceResolution(BaseModel):
    """A source-record-to-subject resolution; uncertainty is a valid persisted state."""

    source_record_id: str
    resolution_status: ResolutionStatus
    resolution_basis: str
    confidence: ResolutionConfidence
    supporting_signals: list[str] = Field(default_factory=list)
    conflicting_signals: list[str] = Field(default_factory=list)
    review_status: Literal["not_required", "pending", "reviewed"] = "not_required"


class SubjectRelationship(BaseModel):
    relationship_type: RelationshipType
    target_causebase_id: str
    evidence_ids: list[str] = Field(default_factory=list)
    note: str | None = None


class CoverageObservation(BaseModel):
    """Machine-readable source/capability status; absence never becomes a negative claim."""

    capability: str
    status: CoverageStatus
    source_record_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    observed_at: date | None = None
    freshness_note: str | None = None


class MoneyObservation(BaseModel):
    """A directly observed amount with source fidelity and exact normalisation."""

    source_amount: Decimal
    source_currency: str = "AUD"
    source_unit_scale: Decimal = Decimal("1")
    normalised_amount: Decimal
    normalised_currency: str = "AUD"
    source_unit_label: str | None = None
    source_raw_value: str | None = None
    source_precision: str | None = None

    @model_validator(mode="after")
    def check_normalisation(self):
        if self.source_unit_scale <= 0:
            raise ValueError("source_unit_scale must be positive")
        if self.source_currency != self.normalised_currency:
            raise ValueError("currency conversion requires an explicit derived value")
        if self.normalised_amount != self.source_amount * self.source_unit_scale:
            raise ValueError("normalised_amount must equal source_amount × source_unit_scale")
        return self


class FundraisingComponent(BaseModel):
    label: str
    amount: MoneyObservation
    evidence_ids: list[str] = Field(default_factory=list)


class FundraisingEstimate(BaseModel):
    normalised_amount: Decimal = Field(ge=0)
    normalised_currency: str = "AUD"
    reporting_period_label: str | None = None
    financial_record_id: str | None = None
    method: DerivationMethod
    confidence: Literal["high", "medium", "low"]
    evidence_ids: list[str] = Field(default_factory=list)
    components: list[FundraisingComponent] = Field(default_factory=list)
    direct_observation: MoneyObservation | None = None
    rule_id: str | None = None
    note: str | None = None
    plausible_low: Decimal | None = Field(default=None, ge=0)
    plausible_high: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def check_range(self):
        if (
            self.plausible_low is not None
            and self.plausible_high is not None
            and self.plausible_low > self.plausible_high
        ):
            raise ValueError("plausible_low cannot exceed plausible_high")
        return self


class FinancialPeriod(BaseModel):
    period_start: date | None = None
    period_end: date | None = None
    period_length_days: int | None = Field(default=None, gt=0)
    label: str | None = None
    is_transitional_or_nonstandard: bool = False

    @model_validator(mode="after")
    def validate_period(self):
        if self.period_start and self.period_end and self.period_start > self.period_end:
            raise ValueError("period_start cannot follow period_end")
        return self


class Financials(BaseModel):
    financial_record_id: str
    period: FinancialPeriod
    reporting_scope: Literal["subject", "organisation_group", "consolidated_group", "unknown"]
    reporting_subject_causebase_id: str | None = None
    covered_subjects: list[str] = Field(default_factory=list)
    consolidated: Literal["true", "false", "unknown"] = "unknown"
    attribution_method: Literal[
        "direct_subject_report",
        "group_scope_report",
        "explicit_allocation",
        "unknown",
    ] = "unknown"
    evidence_ids: list[str] = Field(default_factory=list)
    revenue: MoneyObservation | None = None
    donations: MoneyObservation | None = None
    government_grants: MoneyObservation | None = None
    employee_costs: MoneyObservation | None = None
    total_expenses: MoneyObservation | None = None
    assets: MoneyObservation | None = None
    liabilities: MoneyObservation | None = None


FinancialMetricName = Literal[
    "revenue", "donations", "government_grants", "employee_costs",
    "total_expenses", "assets", "liabilities",
]
ReconciliationStatus = Literal[
    "single_observation", "agreeing", "precision_consistent", "divergent",
    "non_comparable", "unresolved",
]


class FinancialMetricObservation(BaseModel):
    financial_record_id: str
    amount: MoneyObservation
    metric_source_label: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class FinancialMetricSet(BaseModel):
    metric: FinancialMetricName
    observations: list[FinancialMetricObservation] = Field(min_length=1)
    reconciliation_status: ReconciliationStatus
    reconciliation_notes: str | None = None


class Classification(BaseModel):
    taxonomy_id: str
    taxonomy_version: str
    term_id: str
    term_label: str
    assignment_method: Literal[
        "source_native",
        "deterministic_mapping",
        "llm_classification",
        "community_contribution",
        "fixture",
    ]
    confidence: Literal["high", "medium", "low"] | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class EmbeddingMetadata(BaseModel):
    embedding_id: str
    embedding_type: str
    model_id: str
    model_version: str
    dimensions: int = Field(gt=0)
    source_text_hash: str
    generated_at: datetime
    vector_ref: str


class Opportunity(BaseModel):
    opportunity_id: str
    type: Literal[
        "volunteer",
        "working_bee",
        "event",
        "membership",
        "board",
        "committee",
        "advocacy",
        "other",
    ]
    title: str
    location: str | None = None
    source_url: str | None = None
    first_seen: date | None = None
    last_seen: date | None = None
    status: Literal["current", "stale", "unknown"] = "unknown"


class CauseBaseCard(BaseModel):
    causebase_id: str
    subject_kind: SubjectKind = "organisation"
    external_identifiers: list[ExternalIdentifier] = Field(default_factory=list)
    registrations: list[Registration] = Field(default_factory=list)
    tax_statuses: list[TaxStatus] = Field(default_factory=list)
    relationships: list[SubjectRelationship] = Field(default_factory=list)
    source_resolutions: list[SourceResolution] = Field(default_factory=list)
    legal_name: str
    display_name: str
    entity_status: str
    coverage: list[CoverageObservation] = Field(default_factory=list)
    enrichment_level: Literal["registered", "thin", "enriched", "rich"] | None = None

    website: str | None = None
    geography: list[str] = Field(default_factory=list)

    causebase_summary: str
    organisation_self_description: str | None = None

    activities: list[str] = Field(default_factory=list)
    beneficiaries: list[str] = Field(default_factory=list)
    participation_modes: list[str] = Field(default_factory=list)
    opportunities: list[Opportunity] = Field(default_factory=list)

    financial_records: list[Financials] = Field(min_length=1)
    financial_metrics: list[FinancialMetricSet] = Field(default_factory=list)
    fundraising_expenditure: FundraisingEstimate

    classifications: list[Classification] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)

    embedding: EmbeddingMetadata | None = None

    dataset_version: str
    card_schema_version: str = "0.1"
    editorial_policy_version: str = "0.1"
    generator_version: str = "0.1.0"
    built_at: datetime

    @model_validator(mode="after")
    def enriched_card_invariants(self):
        if self.enrichment_level in {"enriched", "rich"}:
            if not self.causebase_summary.strip():
                raise ValueError("enriched card requires a CauseBase summary")
            if self.fundraising_expenditure is None:
                raise ValueError("enriched card requires fundraising estimate")
        evidence_ids = {e.evidence_id for e in self.evidence}
        missing = set(self.fundraising_expenditure.evidence_ids) - evidence_ids
        if missing:
            raise ValueError(f"fundraising evidence IDs missing from card: {sorted(missing)}")
        relationship_missing = {
            evidence_id
            for relationship in self.relationships
            for evidence_id in relationship.evidence_ids
        } - evidence_ids
        if relationship_missing:
            raise ValueError(
                "relationship evidence IDs missing from card: "
                f"{sorted(relationship_missing)}"
            )
        financial_record_ids = {
            financial_record.financial_record_id
            for financial_record in self.financial_records
        }
        if (
            self.fundraising_expenditure.financial_record_id is not None
            and self.fundraising_expenditure.financial_record_id not in financial_record_ids
        ):
            raise ValueError("fundraising estimate references an unknown financial record")
        for metric_set in self.financial_metrics:
            if metric_set.reconciliation_status == "single_observation" and len(metric_set.observations) != 1:
                raise ValueError("single_observation metric must have exactly one observation")
            if metric_set.reconciliation_status != "single_observation" and len(metric_set.observations) < 2:
                raise ValueError("multi-observation reconciliation status requires at least two observations")
            unknown_records = {
                observation.financial_record_id
                for observation in metric_set.observations
            } - financial_record_ids
            if unknown_records:
                raise ValueError(
                    f"financial metric references unknown records: {sorted(unknown_records)}"
                )
        return self

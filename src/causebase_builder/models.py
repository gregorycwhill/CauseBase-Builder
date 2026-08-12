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
    "unknown",
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
    # Retained only so historical fixture data can still be parsed. It is not a
    # permitted Phase 2A publication method.
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
    valid_from: date | None = None
    valid_to: date | None = None
    observed_at: date | None = None
    confidence: Literal["high", "medium", "low"] | None = None
    status: Literal["asserted", "historical", "ended", "uncertain"] = "asserted"

    @model_validator(mode="after")
    def validate_temporal_range(self):
        if self.valid_from and self.valid_to and self.valid_from > self.valid_to:
            raise ValueError("relationship valid_from cannot follow valid_to")
        return self


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


class UnmappedConcept(BaseModel):
    """A private signal that supplied taxonomy terms did not fit cleanly.

    It is deliberately not a classification and cannot introduce a term ID.
    The field is excluded from public card serialisation; periodic taxonomy
    review is the governed route from these observations to a proposal.
    """

    dimension: str
    concept_phrase: str
    evidence_basis: str
    reason_no_supplied_term_fits: str


class TaxonomyAmbiguity(BaseModel):
    """A private signal that two or more supplied terms were hard to distinguish."""

    dimension: str
    candidate_term_ids: list[str] = Field(min_length=2)
    reason: str


class TaxonomyMaintenanceSignals(BaseModel):
    unmapped_concepts: list[UnmappedConcept] = Field(default_factory=list)
    taxonomy_ambiguities: list[TaxonomyAmbiguity] = Field(default_factory=list)


class EmbeddingMetadata(BaseModel):
    embedding_id: str
    embedding_type: str
    model_id: str
    model_version: str
    dimensions: int = Field(gt=0)
    source_text_hash: str
    generated_at: datetime
    vector_ref: str


class SynthesisMetadata(BaseModel):
    """Reproducibility metadata for an evidence-grounded LLM artefact.

    Prompts and raw source excerpts are deliberately excluded from the public
    card: they are private working material. The stable identifiers and hashes
    make an artefact auditable without publishing copied third-party text.
    """

    model_id: str
    prompt_version: str
    parameters: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    evidence_input_hash: str
    generated_at: datetime
    editorial_policy_version: str


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


class SourceNativeRecord(BaseModel):
    """A public-safe, source-specific observation, never a universal claim.

    The record retains source field names and time independently of the
    canonical card. Large raw archives and copyrighted documents remain private.
    """

    source_record_id: str
    source_family: str
    dataset_version: str
    source_url: str | None = None
    retrieved_at: datetime
    observed_at: date | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    source_fields: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    canonical_field_mappings: dict[str, str] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)


class NavigationGeography(BaseModel):
    """Small controlled geography projection used only for navigation."""

    level: Literal["country", "state_territory", "region_locality"]
    code: str
    label: str
    evidence_ids: list[str] = Field(default_factory=list)


class FundingSourceObservation(BaseModel):
    source_type: Literal[
        "government_grants_or_contracts", "individual_donations", "regular_giving",
        "bequests", "major_gifts", "philanthropic_grants", "corporate_support",
        "service_or_earned_income", "investment_income", "other",
    ]
    period_label: str | None = None
    source_label: str | None = None
    amount: MoneyObservation | None = None
    share: Decimal | None = Field(default=None, ge=0, le=1)
    reporting_scope: Literal["subject", "organisation_group", "consolidated_group", "unknown"] = "unknown"
    method: DerivationMethod = "direct_extract"
    evidence_ids: list[str] = Field(default_factory=list)


class FundraisingMethodObservation(BaseModel):
    method: Literal[
        "regular_giving", "face_to_face", "direct_mail", "telephone", "digital_advertising",
        "appeals", "major_donor_program", "bequest_program", "fundraising_events",
        "community_fundraising", "workplace_giving", "peer_to_peer", "corporate_partnerships",
        "raffles_or_lotteries", "other",
    ]
    first_seen: date | None = None
    last_seen: date | None = None
    observed_at: date | None = None
    status: Literal["current", "historical", "stale", "unknown"] = "unknown"
    evidence_ids: list[str] = Field(default_factory=list)


class DerivativeAssessment(BaseModel):
    derivative: Literal["summary", "taxonomy", "fundraising", "embedding", "similarities"]
    generated_at: datetime | None = None
    evidence_through: date | None = None
    last_assessed_at: datetime
    assessment_method: str
    input_hash: str
    disposition: Literal["reused", "refreshed", "not_applicable"]
    reason: str
    affected_dimensions: list[str] = Field(default_factory=list)


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
    navigation_geography: list[NavigationGeography] = Field(default_factory=list)

    causebase_summary: str
    summary_evidence_ids: list[str] = Field(default_factory=list)
    organisation_self_description: str | None = None

    activities: list[str] = Field(default_factory=list)
    beneficiaries: list[str] = Field(default_factory=list)
    participation_modes: list[str] = Field(default_factory=list)
    opportunities: list[Opportunity] = Field(default_factory=list)

    # Source-native observations are intentionally separated from the concise
    # canonical card; consumers can inspect regulator semantics without
    # CauseBase pretending every source field is universal.
    source_native_records: list[SourceNativeRecord] = Field(default_factory=list)

    financial_records: list[Financials] = Field(default_factory=list)
    financial_metrics: list[FinancialMetricSet] = Field(default_factory=list)
    # Some genuine charities do not disclose a defensible fundraising figure.
    # A null is an honest publication state, not permission to use a universal
    # synthetic percentage.
    fundraising_expenditure: FundraisingEstimate | None = None
    funding_sources: list[FundingSourceObservation] = Field(default_factory=list)
    fundraising_methods: list[FundraisingMethodObservation] = Field(default_factory=list)

    classifications: list[Classification] = Field(default_factory=list)
    # These are governed working observations, never public card content and
    # never a route to automatically changing classifications or taxonomy.
    taxonomy_maintenance_signals: TaxonomyMaintenanceSignals | None = Field(default=None, exclude=True)
    evidence: list[EvidenceRef] = Field(default_factory=list)

    embedding: EmbeddingMetadata | None = None
    synthesis: SynthesisMetadata | None = None
    derivative_assessments: list[DerivativeAssessment] = Field(default_factory=list)

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
            # A missing estimate must be accompanied by an explicit coverage
            # observation so downstream users can distinguish it from an
            # accidental omission.
            if self.fundraising_expenditure is None and not any(
                item.capability == "fundraising_expenditure"
                and item.status in {"not_available_from_source", "not_yet_processed", "retrieval_failed", "unknown"}
                for item in self.coverage
            ):
                raise ValueError("enriched card without fundraising estimate requires coverage state")
        capabilities = [item.capability for item in self.coverage]
        if len(capabilities) != len(set(capabilities)):
            raise ValueError("card requires one effective coverage observation per capability")
        evidence_ids = {e.evidence_id for e in self.evidence}
        if self.fundraising_expenditure is not None:
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
        source_native_missing = {
            evidence_id
            for source_record in self.source_native_records
            for evidence_id in source_record.evidence_ids
        } - evidence_ids
        if source_native_missing:
            raise ValueError(f"source-native evidence IDs missing from card: {sorted(source_native_missing)}")
        financial_record_ids = {
            financial_record.financial_record_id
            for financial_record in self.financial_records
        }
        if (
            self.fundraising_expenditure is not None
            and self.fundraising_expenditure.financial_record_id is not None
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
        assessment_names = [assessment.derivative for assessment in self.derivative_assessments]
        if len(assessment_names) != len(set(assessment_names)):
            raise ValueError("card requires one current derivative assessment per derivative")
        return self

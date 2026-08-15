"""Pydantic models for the public 0.5 JSON contract.

Models retain public decimal values as strings; callers must not pass floats.
"""
from __future__ import annotations
from decimal import Decimal
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

ClaimBasis = Literal["direct", "mechanically_derived", "inferred", "estimated"]
CoverageStatus = Literal["observed", "not_found_in_source", "not_available_from_source", "not_applicable", "retrieval_failed", "not_yet_processed", "stale", "unknown"]

class PublicModel(BaseModel): model_config = ConfigDict(extra="forbid")
class SourceReportedMoney(PublicModel):
    source_amount: str; source_currency: str; normalised_amount: str; normalised_currency: str
    source_raw_value: str | None = None; source_unit_scale: str | None = None; source_unit_label: str | None = None; source_precision: str | None = None
    @field_validator("source_amount", "normalised_amount")
    @classmethod
    def decimal_string(cls, value: str) -> str: Decimal(value); return value
class Amount(PublicModel):
    amount: str; currency: str
    @field_validator("amount")
    @classmethod
    def decimal_string(cls, value: str) -> str: Decimal(value); return value
class Capability(PublicModel): capability_id: str; definition: str; observed_when: str; applicability: Literal["all_cards"]
class CapabilityRegistry(PublicModel): registry_id: str; contract_version: Literal["0.5"]; capabilities: list[Capability]
class ReleaseContext(PublicModel):
    release_id: str; dataset_version: str; contract_version: Literal["0.5"] = "0.5"; based_on_release: str; generated_at: str; capability_registry: dict[str, str]
class Coverage(PublicModel):
    capability: str; status: CoverageStatus; assessed_at: str; observation_ids: list[str] = Field(default_factory=list); source_record_ids: list[str] = Field(default_factory=list); evidence_ids: list[str] = Field(default_factory=list); note: str | None = None
class Evidence(PublicModel): evidence_id: str; title: str; url: str | None = None
class Card(PublicModel):
    causebase_id: str; contract_version: Literal["0.5"] = "0.5"; subject_kind: str; identity: dict[str, Any]; release: dict[str, Any]
    source_record_refs: list[str]; source_bindings: list[dict[str, Any]] = Field(default_factory=list); identity_resolution_notice: dict[str, Any] | None = None; evidence: list[Evidence]
    summary: dict[str, Any] | None = None; activities: list[dict[str, Any]] = Field(default_factory=list); beneficiaries: list[dict[str, Any]] = Field(default_factory=list); descriptive_geography: list[dict[str, Any]] = Field(default_factory=list); navigation_geography: list[dict[str, Any]] = Field(default_factory=list); funding_sources: list[dict[str, Any]] = Field(default_factory=list); fundraising_methods: list[dict[str, Any]] = Field(default_factory=list); participation: list[dict[str, Any]] = Field(default_factory=list); opportunities: list[dict[str, Any]] = Field(default_factory=list); programs: list[dict[str, Any]] = Field(default_factory=list); relationships: list[dict[str, Any]] = Field(default_factory=list); classifications: list[dict[str, Any]] = Field(default_factory=list)
    coverage: dict[str, Any]; financial_reports: list[dict[str, Any]] = Field(default_factory=list); canonical_metrics: list[dict[str, Any]] = Field(default_factory=list); current_financials: dict[str, Any] | None = None; analytic_projections: list[dict[str, Any]] = Field(default_factory=list); derivatives: list[dict[str, Any]] = Field(default_factory=list)

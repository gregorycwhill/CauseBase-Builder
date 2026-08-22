"""Deterministic, private Semantic Enrichment Benchmark v1 scaffold.

Steps 1--2 only: this module prepares review material and enumerates bounded
fundraising-industry source arms. It never calls a model and never writes a
public card or release.
"""
from __future__ import annotations

import hashlib
import json
import re
from html.parser import HTMLParser
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


BENCHMARK_VERSION = "semantic-enrichment-benchmark-v1"
DESIGN_AUTHORITY_SHA = "6eaf9cf026b85fce65f847a249c07580417c832c"
PIPELINE_STAGE = "P1"
DOMAINS = (
    "activities", "beneficiaries", "programs", "cause_classification",
    "geography", "participation", "fundraising_practice", "fundraising_campaign",
    "fundraising_provider_relationship", "ethos", "service_mission_orientation",
    "notable_context",
)
BLOCKERS = (
    "IDENTITY_BLOCKED", "ADDITIVITY_BLOCKED", "TIME_SCOPE_UNCLEAR",
    "SCOPE_AMBIGUOUS", "SENSITIVE_REVIEW_REQUIRED",
)


def stable_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


class CohortSubject(BaseModel):
    subject_id: str
    selection_strata: dict[str, str]
    selection_rationale: str
    source_refs: list[str] = Field(default_factory=list)


class CohortManifest(BaseModel):
    version: str = BENCHMARK_VERSION
    purpose: Literal["adversarial_product_economics"] = "adversarial_product_economics"
    subjects: list[CohortSubject]
    selection_config_hash: str

    @model_validator(mode="after")
    def unique_subjects(self):
        ids = [item.subject_id for item in self.subjects]
        if len(ids) != len(set(ids)):
            raise ValueError("cohort subject IDs must be unique")
        return self


class SourceOpportunity(BaseModel):
    subject_id: str
    structured_source_available: bool = False
    website_available: bool = False
    selected_page_roles: list[str] = Field(default_factory=list)
    annual_report: dict[str, Any] = Field(default_factory=dict)
    wikimedia: dict[str, Any] = Field(default_factory=dict)
    fundraising_industry_hits: list[dict[str, Any]] = Field(default_factory=list)
    evidence_volume: int = 0
    relevant_domain_hits: dict[str, int] = Field(default_factory=dict)
    identity_ambiguity_signals: list[str] = Field(default_factory=list)
    refresh_observations: list[str] = Field(default_factory=list)


class IdentityBindingCandidate(BaseModel):
    source_record_id: str
    candidate_subject_id: str | None = None
    status: Literal["resolved", "candidate", "ambiguous", "unresolved"]
    basis: str
    external_identifier: str | None = None


class CandidateScope(BaseModel):
    scope_type: Literal["organisation", "program", "service", "organisational_unit"] = "organisation"
    scope_id: str | None = None
    scope_label: str | None = None


class SemanticCandidate(BaseModel):
    candidate_id: str
    subject_id: str | None = None
    domain: str
    scope: CandidateScope = Field(default_factory=CandidateScope)
    candidate_payload: dict[str, Any] = Field(default_factory=dict)
    claim_basis_proposed: str
    extraction_method: str
    source_family: str
    source_role: str
    source_record_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    source_url: str
    source_location: str
    source_text: str
    source_content_hash: str
    time: dict[str, Any] = Field(default_factory=dict)
    qualification: dict[str, Any] | None = None
    confidence_proposed: str | None = None
    warnings: list[str] = Field(default_factory=list)
    review_status: Literal["review_required"] = "review_required"
    alternative_interpretation: str | None = None
    pipeline_stage: Literal["P0", "P1", "P2", "P3", "O"] = PIPELINE_STAGE


class AssessmentScope(BaseModel):
    subject_id: str
    domain: str
    source_families: list[str] = Field(default_factory=list)
    source_roles: list[str] = Field(default_factory=list)
    reporting_periods: list[str] = Field(default_factory=list)
    policy_version: str = BENCHMARK_VERSION
    processed_at: str | None = None


class CostLedgerEntry(BaseModel):
    subject_id: str | None = None
    domain: str | None = None
    source_family: str | None = None
    source_record_or_location: str | None = None
    stage: Literal["P0", "P1", "P2", "P3", "O", "H2"]
    model: str | None = None
    model_version: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    api_cost_usd: float = 0.0
    elapsed_seconds: float = 0.0
    acquisition_requests: int = 0


class BenchmarkReviewDecision(BaseModel):
    case_id: str
    semantic_outcome: Literal["ACCEPT", "EDIT", "REJECT", "WRONG_DOMAIN", "INSUFFICIENT"]
    blockers: list[Literal[
        "IDENTITY_BLOCKED", "ADDITIVITY_BLOCKED", "TIME_SCOPE_UNCLEAR",
        "SCOPE_AMBIGUOUS", "SENSITIVE_REVIEW_REQUIRED",
    ]] = Field(default_factory=list)
    rationale: str | None = None
    editor_note: str | None = None
    decision_authority: Literal["human_governed"] = "human_governed"

    @model_validator(mode="after")
    def require_rationale_for_non_accept(self):
        if self.semantic_outcome != "ACCEPT" and not self.rationale:
            raise ValueError("non-ACCEPT semantic outcomes require rationale")
        if self.semantic_outcome in {"REJECT", "WRONG_DOMAIN"} and self.blockers:
            raise ValueError("rejected/wrong-domain candidates cannot carry blockers")
        return self


def deterministic_candidate_id(*, subject_id: str | None, domain: str, source_url: str, location: str, text: str) -> str:
    return "seb1-" + stable_hash({"subject_id": subject_id, "domain": domain, "source_url": source_url, "location": location, "text": text})[:16]


def emit_domain_candidates(*, subject_id: str | None, source_url: str, source_family: str, source_role: str, source_record_id: str, passages: list[dict[str, Any]], domain_markers: dict[str, tuple[str, ...]]) -> list[SemanticCandidate]:
    """Emit non-exclusive candidates: one passage may support many domains."""
    result: list[SemanticCandidate] = []
    for passage in passages:
        text = str(passage["text"]); folded = text.casefold()
        for domain, markers in domain_markers.items():
            if not any(marker.casefold() in folded for marker in markers):
                continue
            location = str(passage.get("location", "unknown"))
            result.append(SemanticCandidate(
                candidate_id=deterministic_candidate_id(subject_id=subject_id, domain=domain, source_url=source_url, location=location, text=text),
                subject_id=subject_id, domain=domain,
                candidate_payload={"text": text}, claim_basis_proposed="direct",
                extraction_method="deterministic_source_record", source_family=source_family,
                source_role=source_role, source_record_ids=[source_record_id],
                source_url=source_url, source_location=location, source_text=text,
                source_content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                warnings=["review_only", "not_a_public_claim"],
            ))
    return sorted(result, key=lambda item: item.candidate_id)


class FundraisingIndustryAdapter:
    name: str
    source_family: str
    source_role: str
    source_url: str

    def enumerate_records(self, text: str, *, source_url: str | None = None) -> list[dict[str, Any]]:
        """Parse source-led text deterministically; never infer missing metrics."""
        url = source_url or self.source_url
        records = []
        for index, line in enumerate(text.splitlines(), start=1):
            value = " ".join(line.split())
            if not value or not re.search(r"campaign|award|fundrais|face.to.face|peer.to.peer|agency|provider", value, re.I):
                continue
            records.append({"source_record_id": f"{self.name}:{index}", "source_url": url, "source_location": f"line:{index}", "source_text": value, "metric_wording_preserved": True})
        return records

    def candidates(self, text: str, *, subject_id: str | None = None, source_url: str | None = None) -> list[SemanticCandidate]:
        records = self.enumerate_records(text, source_url=source_url)
        markers = {
            "fundraising_practice": ("face-to-face", "fundraising", "fundraiser", "agency"),
            "fundraising_campaign": ("campaign", "peer-to-peer", "fundraising event", "award"),
            "fundraising_provider_relationship": ("provider", "agency", "platform"),
        }
        return emit_domain_candidates(subject_id=subject_id, source_url=source_url or self.source_url, source_family=self.source_family, source_role=self.source_role, source_record_id=self.name, passages=[{"text": row["source_text"], "location": row["source_location"]} for row in records], domain_markers=markers)


class PFRAAdapter(FundraisingIndustryAdapter):
    name = "pfra"
    source_family = "fundraising_industry_pfra"
    source_role = "fundraising_industry_self_regulatory_association"
    source_url = "https://www.pfra.org.au/"

    def enumerate_html(self, html: str, *, source_url: str | None = None) -> list[dict[str, Any]]:
        """Extract membership labels and retain same-page linked domains."""
        class Parser(HTMLParser):
            def __init__(self):
                super().__init__(); self.href = None; self.buf = []; self.rows = []
            def handle_starttag(self, tag, attrs):
                if tag == "a": self.href = dict(attrs).get("href"); self.buf = []
            def handle_data(self, data):
                if self.href is not None: self.buf.append(data)
            def handle_endtag(self, tag):
                if tag == "a" and self.href is not None:
                    self.rows.append((" ".join(" ".join(self.buf).split()), self.href)); self.href = None
        parser = Parser(); parser.feed(html); records = []
        for index, (label, href) in enumerate(parser.rows, start=1):
            if not label or href.startswith("#") or href.startswith("mailto:"): continue
            low = label.casefold(); kind = "agency_membership" if any(x in low for x in ("agency", "marketing", "consult", "direct", "fundraising")) else "current_charity_membership"
            linked_domain = re.sub(r"^www\.", "", re.sub(r"^https?://", "", href).split("/", 1)[0].casefold())
            if not re.match(r"^https?://", href, re.I) or not linked_domain or linked_domain.endswith("pfra.org.au"): continue
            records.append({"source_record_id": f"{self.name}:anchor:{index}", "source_url": source_url or self.source_url, "source_location": f"anchor:{index}", "source_text": label, "record_type": kind, "linked_website_url": href, "linked_domain": linked_domain, "metric_wording_preserved": True})
        return records

    def enumerate_records(self, text: str, *, source_url: str | None = None) -> list[dict[str, Any]]:
        records = []
        for index, line in enumerate(text.splitlines(), start=1):
            value = " ".join(line.split())
            if not value:
                continue
            low = value.casefold()
            if "face-to-face" in low or "self-regulatory" in low or "higher standard" in low:
                kind = "membership_semantics"
            elif "partnership with" in low or "represents" in low and "fundraising" in low:
                kind = "charity_agency_relationship"
            elif any(term in low for term in ("consultancy", "marketing", "agency", "fundraising results", "direct")):
                kind = "agency_membership"
            elif len(value) < 100 and not any(term in low for term in ("member", "contact", "membership")):
                kind = "current_charity_membership"
            else:
                continue
            records.append({"source_record_id": f"{self.name}:{index}", "source_url": source_url or self.source_url, "source_location": f"line:{index}", "source_text": value, "record_type": kind, "linked_domain": None, "metric_wording_preserved": True})
        return records


class DonorRepublicFunraisinAdapter(FundraisingIndustryAdapter):
    name = "donor_republic_funraisin"
    source_family = "fundraising_industry_p2p_benchmark"
    source_role = "fundraising_industry_benchmark"
    source_url = "https://www.donorrepublic.com.au/"

    def enumerate_records(self, text: str, *, source_url: str | None = None) -> list[dict[str, Any]]:
        """Extract Top-30 rows while retaining report-native metric wording."""
        records = []
        for index, line in enumerate(text.splitlines(), start=1):
            value = " ".join(line.split())
            if not value or not re.search(r"\$|campaign|event|challenge|run|walk|ride|top\s*30", value, re.I):
                continue
            amounts = re.findall(r"(?:AUD\s*)?\$?\s*[0-9][0-9,]*(?:\.\d+)?\s*(?:m|k)?", value, re.I)
            records.append({"source_record_id": f"{self.name}:{index}", "source_url": source_url or self.source_url, "source_location": f"line:{index}", "source_text": value, "campaign_label": value, "reported_amount_2023": amounts[0] if amounts else None, "reported_amount_2024": amounts[1] if len(amounts) > 1 else None, "source_variance": "not_computed", "caveat": "Public revenue may omit offline funds; amounts are source-native benchmark metrics, not accounting revenue."})
        return records

    def enumerate_top30_rows(self, text: str, *, source_url: str | None = None) -> list[dict[str, Any]]:
        rows = self.enumerate_records(text, source_url=source_url)
        unique = {}
        for row in rows:
            amounts = (row.get("reported_amount_2023"), row.get("reported_amount_2024"))
            key = re.sub(r"[^a-z0-9]+", " ", row["source_text"].casefold()).strip()
            if not amounts[0] and not amounts[1]: continue
            unique.setdefault(key, {**row, "record_type": "top30_campaign", "activity_mechanic": "peer-to-peer event", "source_variance": "not_computed"})
        return list(unique.values())[:30]


class FIAAwardsAdapter(FundraisingIndustryAdapter):
    name = "fia_awards"
    source_family = "fundraising_industry_awards"
    source_role = "fundraising_industry_award_record"
    source_url = "https://www.fia.org.au/"

    def enumerate_records(self, text: str, *, source_url: str | None = None) -> list[dict[str, Any]]:
        records = []
        for index, line in enumerate(text.splitlines(), start=1):
            value = " ".join(line.split())
            if not value or not re.search(r"finalist|winner|highly commended|nominated by|campaign|award", value, re.I):
                continue
            status = next((term for term in ("winner", "finalist", "highly commended") if term in value.casefold()), "unspecified")
            match = re.search(r"nominated by:?\s*(.+)$", value, re.I)
            records.append({"source_record_id": f"{self.name}:{index}", "source_url": source_url or self.source_url, "source_location": f"line:{index}", "source_text": value, "record_type": "fia_award_record", "award_year": 2026, "category": None, "organisation": None, "campaign_or_project": None, "status": status, "nominated_by": match.group(1).strip() if match else None, "source_native_category": True})
        return records


ADAPTERS = (PFRAAdapter(), DonorRepublicFunraisinAdapter(), FIAAwardsAdapter())


def build_cohort(subjects: list[dict[str, Any]], *, target: int = 40) -> CohortManifest:
    ordered = sorted(subjects, key=lambda row: str(row.get("subject_id") or row.get("causebase_id") or ""))
    chosen = ordered[:target]
    cohort = [CohortSubject(subject_id=str(row.get("subject_id") or row.get("causebase_id")), selection_strata={k: str(row.get(k, "unknown")) for k in ("size", "source_richness", "annual_report", "website", "complexity", "fundraising_intensity")}, selection_rationale="Deterministic adversarial benchmark selection; cohort membership is not salience.", source_refs=list(row.get("source_refs", []))) for row in chosen]
    config_hash = stable_hash({"target": target, "subject_ids": [x.subject_id for x in cohort]})
    return CohortManifest(subjects=cohort, selection_config_hash=config_hash)


def source_opportunities(cohort: CohortManifest, *, source_rows: dict[str, dict[str, Any]] | None = None) -> list[SourceOpportunity]:
    source_rows = source_rows or {}
    return [SourceOpportunity(subject_id=item.subject_id, **{key: value for key, value in source_rows.get(item.subject_id, {}).items() if key in SourceOpportunity.model_fields}) for item in cohort.subjects]


def conservative_identity_candidates(*, source_record_id: str, external_identifier: str | None, known_identifiers: dict[str, str]) -> IdentityBindingCandidate:
    """Resolve only an exact governed identifier; names never resolve identity."""
    if external_identifier and external_identifier in known_identifiers:
        return IdentityBindingCandidate(source_record_id=source_record_id, candidate_subject_id=known_identifiers[external_identifier], status="resolved", basis="exact_governed_external_identifier", external_identifier=external_identifier)
    return IdentityBindingCandidate(source_record_id=source_record_id, status="unresolved", basis="no_exact_governed_identifier", external_identifier=external_identifier)


def crosswalk_source_records(records: list[dict[str, Any]], *, known_domains: dict[str, str]) -> list[dict[str, Any]]:
    """Crosswalk source labels conservatively; exact domains resolve, names remain candidates."""
    output = []
    for record in records:
        label = str(record.get("organisation") or record.get("charity") or record.get("charity_label") or "").strip()
        domain = str(record.get("linked_domain") or "").casefold().strip()
        if domain and domain in known_domains:
            binding = {"status": "resolved", "subject_id": known_domains[domain], "basis": "exact_known_domain"}
        elif label:
            binding = {"status": "candidate", "subject_id": None, "basis": "name_only_candidate"}
        else:
            binding = {"status": "unresolved", "subject_id": None, "basis": "no_identity_signal"}
        output.append({**record, "identity_binding": binding})
    return output


def selection_matrix(population: list[dict[str, Any]], crosswalk: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hits = Counter(str(row.get("source_family")) for row in crosswalk if row.get("identity_binding", {}).get("status") == "resolved")
    by_label = Counter(str(row.get("organisation") or row.get("charity") or row.get("charity_label") or "").casefold() for row in crosswalk)
    matrix = []
    for card in population:
        label = str(card.get("display_name") or card.get("legal_name") or "")
        matrix.append({"subject_id": card.get("causebase_id"), "display_name": label, "size": card.get("size", "unknown"), "website_richness": "available" if card.get("website") else "unknown", "report_richness": "available" if card.get("financial_records") else "unknown", "source_richness": "structured" if card.get("evidence") else "thin", "complexity_identity_signals": ["identity_ambiguity"] if card.get("subject_kind") in {"unknown", "organisation_group"} else [], "fundraising_industry_hit_count": by_label.get(label.casefold(), 0), "fundraising_industry_hit_types": sorted({str(row.get("source_family")) for row in crosswalk if str(row.get("organisation") or row.get("charity") or row.get("charity_label") or "").casefold() == label.casefold()}), "selection_status": "available_for_user_selection", "governed_cohort_selected": False})
    return matrix


def assessment_scopes(opportunities: list[SourceOpportunity], processed: list[dict[str, Any]] | None = None) -> list[AssessmentScope]:
    """Report only source families/roles actually processed successfully."""
    rows = processed or []
    return [AssessmentScope(subject_id=row["subject_id"], domain=row["domain"], source_families=sorted(set(row.get("source_families", []))), source_roles=sorted(set(row.get("source_roles", [])))) for row in rows if row.get("source_families") and row.get("source_roles")]


def prepare_review_packet(candidates: list[SemanticCandidate], *, target: int = 48) -> list[dict[str, Any]]:
    rows = sorted(candidates, key=lambda item: item.candidate_id)[:target]
    return [{"case_id": item.candidate_id, "subject_id": item.subject_id, "domain": item.domain, "source_url": item.source_url, "source_location": item.source_location, "source_excerpt": item.source_text, "candidate_payload": item.candidate_payload, "reviewer_question": "Does this evidence support the proposed bounded observation?"} for item in rows]


def benchmark_summary(cohort: CohortManifest, opportunities: list[SourceOpportunity], candidates: list[SemanticCandidate], adapter_results: list[dict[str, Any]]) -> dict[str, Any]:
    return {"version": BENCHMARK_VERSION, "design_authority_sha": DESIGN_AUTHORITY_SHA, "pipeline_stage": PIPELINE_STAGE, "cohort_subjects": len(cohort.subjects), "candidate_count": len(candidates), "candidates_by_domain": dict(sorted(Counter(item.domain for item in candidates).items())), "candidates_by_source_family": dict(sorted(Counter(item.source_family for item in candidates).items())), "source_opportunity_count": len(opportunities), "adapter_results": adapter_results, "model_calls": {"P2": 0, "P3": 0, "O": 0}, "review_only": True}


def prepare_benchmark(*, subjects: list[dict[str, Any]], output_dir: Path, target: int = 40, adapter_text: dict[str, str] | None = None) -> dict[str, Any]:
    """Run deterministic PREPARE and write only private output files."""
    cohort = build_cohort(subjects, target=target); opportunities = source_opportunities(cohort)
    adapter_text = adapter_text or {}
    candidates: list[SemanticCandidate] = []; adapter_results = []
    for adapter in ADAPTERS:
        text = adapter_text.get(adapter.name, "")
        found = adapter.candidates(text) if text else []
        candidates.extend(found)
        adapter_results.append({"adapter": adapter.name, "source_family": adapter.source_family, "source_url": adapter.source_url, "status": "enumerated" if text else "not_acquired", "record_count": len(adapter.enumerate_records(text)) if text else 0, "candidate_count": len(found), "reason": None if text else "No authorised local source snapshot supplied; adapter remains bounded and review-only."})
    scopes = assessment_scopes(opportunities, [{"subject_id": item.subject_id, "domain": item.domain, "source_families": [item.source_family], "source_roles": [item.source_role]} for item in candidates if item.subject_id])
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "cohort.json").write_text(cohort.model_dump_json(indent=2), encoding="utf-8")
    (output_dir / "source-opportunity-inventory.json").write_text(json.dumps([x.model_dump(mode="json") for x in opportunities], indent=2), encoding="utf-8")
    (output_dir / "candidate-inventory.jsonl").write_text("".join(item.model_dump_json() + "\n" for item in candidates), encoding="utf-8")
    (output_dir / "assessment-scope.jsonl").write_text("".join(item.model_dump_json() + "\n" for item in scopes), encoding="utf-8")
    (output_dir / "cost-ledger.jsonl").write_text("".join(CostLedgerEntry(subject_id=item.subject_id, stage="P1", source_family="structured_baseline").model_dump_json() + "\n" for item in cohort.subjects), encoding="utf-8")
    packet = prepare_review_packet(candidates); (output_dir / "HUMAN_REVIEW_PACKAGE.md").write_text("# Semantic Enrichment Benchmark v1 — review-only\n\n" + "\n".join(f"- `{row['case_id']}` — {row['domain']}: {row['source_excerpt']}" for row in packet), encoding="utf-8")
    summary = benchmark_summary(cohort, opportunities, candidates, adapter_results); (output_dir / "benchmark-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary

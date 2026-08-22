"""Deterministic, private Semantic Enrichment Benchmark v1 scaffold.

Steps 1--2 only: this module prepares review material and enumerates bounded
fundraising-industry source arms. It never calls a model and never writes a
public card or release.
"""
from __future__ import annotations

import hashlib
import json
import re
import csv
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


def normalize_host(value: str | None) -> str | None:
    if not value: return None
    host = re.sub(r"^https?://", "", str(value).strip(), flags=re.I).split("/", 1)[0].split(":", 1)[0].casefold()
    return host.removeprefix("www.") or None


def normalize_v05_population(payload: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Read the nested immutable v0.5 identity contract into crosswalk rows."""
    entities = payload.get("entities", []) if isinstance(payload, dict) else payload
    rows = []
    for card in entities:
        # Immutable v0.5 cards in circulation use the identity fields directly;
        # accept the nested contract as well so the crosswalk is schema-aware.
        identity = card.get("identity") or card
        identifiers = identity.get("external_identifiers", []) or card.get("external_identifiers", []) or []
        rows.append({
            "subject_id": card.get("causebase_id") or identity.get("causebase_id"),
            "display_name": identity.get("display_name"),
            "legal_name": identity.get("legal_name"),
            "operating_names": identity.get("operating_names", []) or [],
            "website": identity.get("website"),
            "website_domain": normalize_host(identity.get("website")),
            "external_identifiers": identifiers,
            "subject_kind": card.get("subject_kind") or identity.get("subject_kind"),
            "identity_ambiguity_signals": card.get("identity_ambiguity_signals", []) or identity.get("ambiguity_signals", []) or [],
            "report_available": bool(card.get("financial_records") or card.get("annual_reports") or card.get("reports")),
            "evidence_available": bool(card.get("evidence")),
            "financial_available": bool(card.get("financial_records") or card.get("financial_metrics")),
        })
    return rows


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
        if not records:
            for index, line in enumerate(lines, start=1):
                if not re.search(r"finalist|winner|commend|nominated by|campaign|award", line, re.I): continue
                match = re.search(r"nominated by:?\s*(.+)$", line, re.I)
                records.append({"source_record_id": f"{self.name}:{index}", "source_url": source_url or self.source_url, "source_location": f"line:{index}", "source_text": line, "record_type": "fia_award_record", "year": 2026, "source_native_award_category": None, "organisation": None, "campaign_project": line, "status": "winner" if "winner" in line.casefold() else "finalist", "consultant_service_provider": None, "nominated_by": match.group(1).strip() if match else None})
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

    def enumerate_html(self, html: str, *, source_url: str | None = None, directory_role: Literal["current_charity_membership", "agency_membership"] = "current_charity_membership") -> list[dict[str, Any]]:
        """Extract membership labels and retain same-page linked domains."""
        class Parser(HTMLParser):
            def __init__(self):
                super().__init__(); self.href = None; self.buf = []; self.rows = []; self.titles = []; self.title = None; self.title_buf = []
            def handle_starttag(self, tag, attrs):
                if tag == "a": self.href = dict(attrs).get("href"); self.buf = []
                elif tag == "h4": self.title_buf = []
            def handle_data(self, data):
                if self.href is not None: self.buf.append(data)
                elif self.title_buf is not None: self.title_buf.append(data)
            def handle_endtag(self, tag):
                if tag == "h4":
                    value = " ".join(" ".join(self.title_buf).split()); self.title = value or None
                    if self.title: self.titles.append(self.title)
                    self.title_buf = []
                if tag == "a" and self.href is not None:
                    self.rows.append((" ".join(" ".join(self.buf).split()), self.href, self.title)); self.href = None
        parser = Parser(); parser.feed(html); records = []
        seen = set()
        for index, (label, href, member_title) in enumerate(parser.rows, start=1):
            if not label or href.startswith("#") or href.startswith("mailto:"): continue
            kind = directory_role
            linked_domain = normalize_host(href)
            if not re.match(r"^https?://", href, re.I) or not linked_domain or linked_domain.endswith("pfra.org.au"): continue
            member_label = member_title or label
            identity_key = (kind, member_label.casefold(), linked_domain)
            if identity_key in seen: continue
            seen.add(identity_key)
            records.append({"source_record_id": f"{self.name}:member:{len(seen)}", "source_url": source_url or self.source_url, "source_location": f"anchor:{index}", "source_text": member_label, "record_type": kind, "charity_label": member_label if kind == "current_charity_membership" else None, "agency_label": member_label if kind == "agency_membership" else None, "linked_website_url": href, "linked_domain": linked_domain, "metric_wording_preserved": True})
        if directory_role == "agency_membership":
            linked_titles = {r.get("source_text") for r in records}
            for title in parser.titles:
                if title in {"Fundraising Agency Members", "Charity Members"} or title in linked_titles: continue
                key = (directory_role, title.casefold(), None)
                if key in seen: continue
                seen.add(key)
                records.append({"source_record_id": f"{self.name}:member:{len(seen)}", "source_url": source_url or self.source_url, "source_location": "heading:member", "source_text": title, "record_type": directory_role, "charity_label": None, "agency_label": title, "linked_website_url": None, "linked_domain": None, "metric_wording_preserved": True})
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
    source_family = "fundraising_industry_benchmark"
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
        rows = []
        for index, line in enumerate(text.splitlines(), start=1):
            value = " ".join(line.split())
            match = re.match(r"^\s*(\d{1,2})\s*[|\t]\s*(.+)$", line)
            if match:
                parts = [x.strip() for x in re.split(r"\||\t", line) if x.strip()]
                if len(parts) >= 3 and 1 <= int(match.group(1)) <= 30:
                    amounts = re.findall(r"(?:AUD\s*)?\$?\s*[0-9][0-9,]*(?:\.\d+)?\s*(?:m|k)?", value, re.I)
                    rows.append({"source_record_id": f"{self.name}:row:{match.group(1)}", "source_url": source_url or self.source_url, "source_location": f"row:{match.group(1)}", "source_text": value, "record_type": "top30_campaign", "rank": int(match.group(1)), "campaign_event_name": parts[1], "charity_source_organisation_label": parts[2], "activity_mechanic": parts[3] if len(parts) > 3 else None, "reported_amount_2023": amounts[0] if amounts else None, "reported_amount_2024": amounts[1] if len(amounts) > 1 else None, "source_reported_variance": parts[5] if len(parts) > 5 else None, "reporting_year": 2024, "source_edition": "Top 30 for 2024", "offline_revenue_caveat": "Public revenue may omit offline funds."})
        if rows: return rows[:30]
        # pdf text extraction represents the actual table as whitespace columns.
        # Parse only rows between the table header and TOTALS, never narrative
        # mentions elsewhere in the report.
        in_table = False
        activities = ("Walk & Run", "Run & Cycling", "Cycling", "Hosted", "Shave", "Sleep Rough", "Give Up", "Steps", "Walk", "Swim", "Trek", "Dancing")
        for index, line in enumerate(text.splitlines(), start=1):
            value = " ".join(line.split())
            if "The 2024 Top 30" in value and "Revenue" in value:
                in_table = True; continue
            if in_table and value.startswith("TOTALS"):
                break
            if not in_table: continue
            amounts = re.findall(r"\$[0-9][0-9,]*(?:\.\d+)?", value)
            variance = re.search(r"(-?\d+)%\s*$", value)
            if len(amounts) < 2 or not variance: continue
            prefix = value[:value.rfind(amounts[0])].strip()
            rank = len(rows) + 1
            mechanic = next((a for a in activities if prefix.casefold().endswith(a.casefold())), None)
            if mechanic: prefix = prefix[:-len(mechanic)].strip()
            tokens = prefix.split()
            if not tokens: continue
            # Preserve the source text and keep both logical fields populated;
            # the source does not provide a separate machine-readable delimiter.
            charity = tokens[-1]
            campaign = " ".join(tokens[:-1]) or charity
            rows.append({"source_record_id": f"{self.name}:row:{rank}", "source_url": source_url or self.source_url, "source_location": f"line:{index}", "source_text": value, "record_type": "top30_campaign", "rank": rank, "campaign_event_name": campaign, "charity_source_organisation_label": charity, "activity_mechanic": mechanic, "reported_amount_2023": amounts[0], "reported_amount_2024": amounts[1], "source_reported_variance": variance.group(1) + "%", "reporting_year": 2024, "source_edition": "Top 30 for 2024", "offline_revenue_caveat": "Public revenue may omit offline funds."})
        return rows[:30]


class FIAAwardsAdapter(FundraisingIndustryAdapter):
    name = "fia_awards"
    source_family = "fundraising_industry_awards"
    source_role = "fundraising_industry_award_record"
    source_url = "https://www.fia.org.au/"

    def enumerate_html(self, html: str, *, source_url: str | None = None, page_status: str = "finalist") -> list[dict[str, Any]]:
        class Parser(HTMLParser):
            def __init__(self): super().__init__(); self.tag = None; self.buf = []; self.heading = ""; self.items = []
            def handle_starttag(self, tag, attrs):
                if tag in {"h1", "h2", "h3", "h4", "p", "li"}: self.tag = tag; self.buf = []
            def handle_data(self, data):
                if self.tag: self.buf.append(data)
            def handle_endtag(self, tag):
                if tag == self.tag:
                    text = " ".join(" ".join(self.buf).split());
                    if text and tag.startswith("h"): self.heading = text
                    elif text: self.items.append((self.heading, text))
                    self.tag = None
        parser = Parser(); parser.feed(html); records = []
        index = 0
        while index < len(parser.items):
            category, text = parser.items[index]
            if re.search(r"nominated by", text, re.I):
                index += 1; continue
            nxt = parser.items[index + 1][1] if index + 1 < len(parser.items) and parser.items[index + 1][0] == category else None
            if not nxt and not re.search(r"campaign|appeal|project|winner|finalist|commend", text, re.I):
                index += 1; continue
            organisation, campaign = (text, nxt) if nxt else (None, text)
            nominated_by = None
            if index + 2 < len(parser.items) and parser.items[index + 2][0] == category and re.search(r"nominated by", parser.items[index + 2][1], re.I):
                nominated_by = re.sub(r"^.*?nominated by:?\s*", "", parser.items[index + 2][1], flags=re.I).strip()
                index += 1
            records.append({"source_record_id": f"{self.name}:html:{len(records)+1}", "source_url": source_url or self.source_url, "source_location": f"item:{index+1}", "source_text": " — ".join(x for x in (organisation, campaign) if x), "record_type": "fia_award_record", "year": 2026, "source_native_award_category": category or None, "organisation": organisation, "campaign_project": campaign, "status": page_status, "consultant_service_provider": organisation if category and re.search(r"consultant|service partner", category, re.I) else None, "nominated_by": nominated_by})
            index += 2
        return records

    def enumerate_records(self, text: str, *, source_url: str | None = None) -> list[dict[str, Any]]:
        records = []; category = None; lines = [" ".join(x.split()) for x in text.splitlines() if x.strip()]
        provider_category = False; i = 0
        category_markers = ("CAMPAIGN", "SUPPORTER", "PARTNERSHIP", "EVENT", "GIFT", "CONSULTANT", "SERVICE PARTNER")
        while i < len(lines):
            value = lines[i]
            if value.upper() == "STATE WINNERS" or any(marker in value.upper() for marker in category_markers):
                category = value; provider_category = bool(re.search(r"consultant|service partner", value, re.I)); i += 1; continue
            if category and i + 1 < len(lines) and not re.search(r"nominated by|commend|winner|finalist", value, re.I):
                next_value = lines[i + 1]
                nominated = None; campaign = next_value
                if re.search(r"nominated by", next_value, re.I):
                    nominated = re.sub(r"^.*?nominated by:?\s*", "", next_value, flags=re.I).strip(); campaign = None
                elif i + 2 < len(lines) and re.search(r"nominated by", lines[i + 2], re.I):
                    nominated = re.sub(r"^.*?nominated by:?\s*", "", lines[i + 2], flags=re.I).strip()
                records.append({"source_record_id": f"{self.name}:{i+1}", "source_url": source_url or self.source_url, "source_location": f"line:{i+1}", "source_text": " — ".join(x for x in (value, campaign) if x), "record_type": "fia_award_record", "year": 2026, "source_native_award_category": category, "organisation": value, "campaign_project": campaign, "status": "high commendation" if "commend" in value.casefold() else "winner" if "winner" in value.casefold() else "finalist", "consultant_service_provider": value if provider_category else None, "nominated_by": nominated})
                i += 3 if nominated and campaign else 2; continue
            i += 1
        if not records:
            for index, line in enumerate(lines, start=1):
                if not re.search(r"finalist|winner|commend|nominated by|campaign|award", line, re.I): continue
                match = re.search(r"nominated by:?\s*(.+)$", line, re.I)
                records.append({"source_record_id": f"{self.name}:{index}", "source_url": source_url or self.source_url, "source_location": f"line:{index}", "source_text": line, "record_type": "fia_award_record", "year": 2026, "source_native_award_category": None, "organisation": None, "campaign_project": line, "status": "winner" if "winner" in line.casefold() else "finalist", "consultant_service_provider": None, "nominated_by": match.group(1).strip() if match else None})
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


def crosswalk_source_records(records: list[dict[str, Any]], *, known_domains: dict[str, str | list[str]], known_names: dict[str, list[str]] | None = None) -> list[dict[str, Any]]:
    """Crosswalk source labels conservatively; exact domains resolve, names remain candidates."""
    output = []
    for record in records:
        label = str(record.get("organisation") or record.get("charity") or record.get("charity_label") or "").strip()
        domain = normalize_host(record.get("linked_domain"))
        if domain and domain in known_domains:
            matches = known_domains[domain] if isinstance(known_domains[domain], list) else [known_domains[domain]]
            binding = {"status": "resolved" if len(matches) == 1 else "ambiguous", "subject_id": matches[0] if len(matches) == 1 else None, "basis": "exact_known_domain"}
        elif label:
            matches = (known_names or {}).get(label.casefold(), [])
            binding = {"status": "ambiguous" if len(matches) > 1 else "candidate", "subject_id": None, "basis": "name_only_candidate", "name_matches": matches}
        else:
            binding = {"status": "unresolved", "subject_id": None, "basis": "no_identity_signal"}
        output.append({**record, "identity_binding": binding})
    return output


def build_acnc_backbone_index(source_records: list[dict[str, Any]]) -> dict[str, Any]:
    """Index the national ACNC register without minting CauseBase subjects."""
    domains: dict[str, list[dict[str, Any]]] = {}; names: dict[str, list[dict[str, Any]]] = {}; abns: dict[str, dict[str, Any]] = {}
    for record in source_records:
        fields = record.get("source_fields", {}) or record.get("source_payload", {}) or {}
        name = fields.get("Legal Name") or fields.get("Charity_Legal_Name") or fields.get("Name") or fields.get("legal_name")
        website = fields.get("Website") or fields.get("Charity_Website") or fields.get("website")
        abn = str(fields.get("ABN") or fields.get("abn") or "").replace(" ", "") or None
        row = {"abn": abn, "legal_name": name, "website": website, "source_record_id": record.get("source_record_id"), "source_url": record.get("source_url")}
        if abn: abns[abn] = row
        if name: names.setdefault(str(name).casefold(), []).append(row)
        domain = normalize_host(website)
        if domain: domains.setdefault(domain, []).append(row)
    return {"domains": domains, "names": names, "abns": abns}


def load_national_acnc_backbone(path: Path, *, minimum_records: int = 10_000) -> dict[str, Any]:
    """Load the existing normalized national register; reject benchmark-only inputs."""
    if not path.exists():
        raise FileNotFoundError(path)
    records = []
    with path.open(encoding="utf-8-sig", errors="ignore", newline="") as handle:
        for row in csv.DictReader(handle):
            records.append({"source_record_id": f"acnc-register:{row.get('ABN','')}", "source_fields": row})
    if len(records) < minimum_records:
        raise ValueError(f"national ACNC backbone requires >= {minimum_records} records; got {len(records)}")
    index = build_acnc_backbone_index(records)
    index.update({"source_artifact": str(path), "input_record_count": len(records), "indexed_abn_count": len(index["abns"]), "indexed_legal_name_count": len(index["names"]), "indexed_website_domain_count": len(index["domains"]), "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    return index


def crosswalk_against_acnc(records: list[dict[str, Any]], index: dict[str, Any]) -> list[dict[str, Any]]:
    """Bind industry observations to ACNC records, keeping names review-only."""
    output = []
    for record in records:
        domain = normalize_host(record.get("linked_domain")); label = str(record.get("organisation") or record.get("charity_label") or record.get("agency_label") or record.get("charity_source_organisation_label") or "").strip()
        matches = index.get("domains", {}).get(domain, []) if domain else []
        basis = "exact_authoritative_domain" if matches else "name_only_review_candidate"
        if not matches and label: matches = index.get("names", {}).get(label.casefold(), [])
        status = "resolved" if domain and len(matches) == 1 else "ambiguous" if len(matches) > 1 else "candidate" if label else "unresolved"
        output.append({**record, "acnc_identity": {"status": status, "basis": basis if matches else "no_identity_signal", "matches": matches}})
    return output


def selection_matrix(population: list[dict[str, Any]], crosswalk: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_subject = Counter(row.get("identity_binding", {}).get("subject_id") for row in crosswalk if row.get("identity_binding", {}).get("subject_id"))
    by_label = Counter(str(row.get("organisation") or row.get("charity") or row.get("charity_label") or "").casefold() for row in crosswalk if row.get("identity_binding", {}).get("status") in {"candidate", "ambiguous"})
    matrix = []
    for card in population:
        label = str(card.get("display_name") or card.get("legal_name") or ""); sid = card.get("subject_id") or card.get("causebase_id")
        linked = [row for row in crosswalk if row.get("identity_binding", {}).get("subject_id") == sid or sid in row.get("identity_binding", {}).get("name_matches", []) or (str(row.get("organisation") or row.get("charity") or row.get("charity_label") or "").casefold() == label.casefold() and row.get("identity_binding", {}).get("status") in {"candidate", "ambiguous"})]
        matrix.append({"subject_id": sid, "display_name": label, "size": card.get("size", "unknown"), "website_richness": "available" if card.get("website") or card.get("website_domain") else "unknown", "report_richness": "available" if card.get("financial_records") or card.get("report_available") else "unknown", "source_richness": "structured" if card.get("evidence") or card.get("evidence_available") else "thin", "complexity_identity_signals": card.get("identity_ambiguity_signals", []), "fundraising_industry_hit_count": len(linked), "fundraising_industry_hit_types": sorted({str(row.get("source_family")) for row in linked}), "exact_industry_hit": any(row.get("identity_binding", {}).get("subject_id") == sid for row in linked), "candidate_industry_hit": any(row.get("identity_binding", {}).get("status") in {"candidate", "ambiguous"} for row in linked), "selection_status": "available_for_user_selection", "governed_cohort_selected": False})
    return matrix


def assessment_scopes(opportunities: list[SourceOpportunity], processed: list[dict[str, Any]] | None = None) -> list[AssessmentScope]:
    """Report only source families/roles actually processed successfully."""
    rows = processed or []
    return [AssessmentScope(subject_id=row["subject_id"], domain=row["domain"], source_families=sorted(set(row.get("source_families", []))), source_roles=sorted(set(row.get("source_roles", [])))) for row in rows if row.get("source_families") and row.get("source_roles")]


def prepare_review_packet(candidates: list[SemanticCandidate], *, target: int = 48) -> list[dict[str, Any]]:
    # Stratify deterministically across available domain/source-family pairs.
    buckets: dict[tuple[str, str], list[SemanticCandidate]] = {}
    for item in candidates:
        if re.search(r"<\s*(?:!doctype|html|div|script|style)\b", item.source_text, re.I):
            continue
        buckets.setdefault((item.domain, item.source_family), []).append(item)
    rows = []
    for key in sorted(buckets):
        rows.append(sorted(buckets[key], key=lambda item: item.candidate_id)[0])
    if len(rows) < target:
        used = {item.candidate_id for item in rows}
        rows.extend(item for item in sorted(candidates, key=lambda item: item.candidate_id) if item.candidate_id not in used and not re.search(r"<\s*(?:!doctype|html|div|script|style)\b", item.source_text, re.I))
    rows = rows[:target]
    return [{"case_id": item.candidate_id, "subject_id": item.subject_id, "domain": item.domain, "source_url": item.source_url, "source_location": item.source_location, "source_excerpt": item.source_text, "candidate_payload": item.candidate_payload, "reviewer_question": "Does this evidence support the proposed bounded observation?"} for item in rows]


def structured_p1_candidates(*, benchmark_case_id: str, records: list[dict[str, Any]], source_family: str) -> list[dict[str, Any]]:
    """Generate review-only P1 candidates from logical records, never raw markup."""
    output = []
    for record in records:
        text = str(record.get("source_text") or record.get("campaign_event_name") or record.get("organisation") or "").strip()
        if not text or re.search(r"<\s*(?:!doctype|html|div|script|style)\b", text, re.I):
            continue
        domains = []
        if record.get("record_type") == "top30_campaign": domains = ["fundraising_campaign"]
        elif record.get("record_type") in {"current_charity_membership", "membership_semantics"}: domains = ["fundraising_practice"]
        elif record.get("record_type") == "fia_award_record": domains = ["fundraising_campaign"] + (["fundraising_provider_relationship"] if record.get("nominated_by") or record.get("consultant_service_provider") else [])
        for domain in domains:
            output.append({"benchmark_case_id": benchmark_case_id, "source_record_id": record.get("source_record_id"), "evidence_slice": text, "candidate_domain": domain, "source_family": source_family, "deterministic_rule": f"structured_{record.get('record_type')}", "review_only": True})
    return output


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

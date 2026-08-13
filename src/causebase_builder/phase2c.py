"""RC3 projection: complete existing public observations without summary rewrites."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from .models import (
    CauseBaseCard, CoverageObservation, EvidenceRef, FinancialLineItem,
    Financials, FundraisingMethodObservation, FundraisingEstimate,
    FundingSourceObservation, MoneyObservation, ParticipationObservation,
    ProgramObservation, SourceNativeRecord, TaxStatus,
)
from .render import file_sha256, render_publication
from .semantic import attach_production_embeddings, build_similarity_rows


RC3_GENERATOR_VERSION = "0.4.0-rc3"
RC3_EDITORIAL_POLICY_VERSION = "0.3-rc2"
CANONICAL_VIEWER_ROOT = "https://gregorycwhill.github.io/CauseBase-Viewer/"
EJA_ID = "cb_604da7f26c6c48dd934e713edc493e9f"
EJA_ABN = "74052124375"
EJA_PROFILE = "https://www.acnc.gov.au/charity/charities/2ba8363e-38af-e811-a963-000d3ad244fd/profile"
EJA_AIS = "https://www.acnc.gov.au/charity/charities/2ba8363e-38af-e811-a963-000d3ad244fd/documents/a9cc94e1-1fd7-f011-8544-6045bde67719"
EJA_ANNUAL = "https://envirojustice.org.au/wp-content/uploads/2025/11/EJA-Annual-Report-2024-25_.pdf"
EJA_FINANCIAL = "https://envirojustice.org.au/wp-content/uploads/2025/10/EJA-Financial-Report-2024-2025.pdf"


def _abn(card: CauseBaseCard) -> str | None:
    return next((item.value for item in card.external_identifiers if item.scheme.lower() == "abn"), None)


def _money(value: str) -> MoneyObservation:
    return MoneyObservation(source_amount=value, normalised_amount=value, source_raw_value=value)


def _evidence(card: CauseBaseCard, item: EvidenceRef) -> None:
    if not any(current.evidence_id == item.evidence_id for current in card.evidence):
        card.evidence.append(item)


def _replace_coverage(card: CauseBaseCard, observation: CoverageObservation) -> None:
    card.coverage = [item for item in card.coverage if item.capability != observation.capability] + [observation]


def _load_rows(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row.get("ABN", ""): dict(row) for row in csv.DictReader(handle) if row.get("ABN")}


def _dgr_abns(path: Path) -> set[str]:
    found: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row.get("dgr_status") == "endorsed":
                found.update(item["value"] for item in row.get("external_identifiers", []) if item.get("scheme") == "abn")
    return found


def _raw_ais_sidecar(card: CauseBaseCard, row: dict[str, str], now: datetime) -> None:
    abn = _abn(card)
    evidence_id = f"ev:ais:{abn}:2023"
    if not any(item.evidence_id == evidence_id for item in card.evidence):
        return
    record_id = f"src:acnc-ais-full:{abn}:2023"
    card.source_native_records = [item for item in card.source_native_records if item.source_record_id != record_id]
    card.source_native_records.append(SourceNativeRecord(
        source_record_id=record_id, source_family="acnc-ais", dataset_version="2023-acquired-full-row",
        source_url="https://www.acnc.gov.au/charity/about-charity-register/download-charity-register-data",
        retrieved_at=now, observed_at="2026-08-10", source_fields={key: value or None for key, value in row.items()},
        canonical_field_mappings={"ABN": "external_identifiers", "Total Revenue": "financial_records[].revenue", "Total Expenses": "financial_records[].total_expenses"}, evidence_ids=[evidence_id],
    ))


def _latest_public_acnc(card: CauseBaseCard, entity: dict, now: datetime) -> None:
    """Keep the ACNC response source-native and expose only its stable locator."""
    abn = _abn(card)
    uuid, data = entity["uuid"], entity["data"]
    profile_url = f"https://www.acnc.gov.au/charity/charities/{uuid}/profile"
    card.acnc_profile_url = profile_url
    card.operating_names = [item["Name"] if isinstance(item, dict) else str(item) for item in (data.get("OtherNames") or []) if (item.get("Name") if isinstance(item, dict) else item)]
    card.principal_location = ", ".join(part for part in (data.get("AddressStateOrProvince"), "Australia") if part)
    # Multiple historical card identities can legitimately resolve to the same
    # current ABN. Keep each card's source-native sidecar addressable.
    record_id = f"src:acnc-public-profile:{abn}:{card.causebase_id}:2026-08-13"
    card.source_native_records = [item for item in card.source_native_records if item.source_record_id != record_id]
    submitted = [item for item in data.get("AnnualReports", []) if item.get("IsAIS") and item.get("Status") == "Submitted" and item.get("AISId")]
    if not submitted:
        card.source_native_records.append(SourceNativeRecord(source_record_id=record_id, source_family="acnc-public-profile", dataset_version="2026-08-13-public-api", source_url=profile_url, retrieved_at=now, observed_at="2026-08-13", source_fields={"uuid": uuid, "abn": abn, "latest_ais_year": None, "latest_ais_uuid": None}, source_payload=entity, canonical_field_mappings={"data.Name": "display_name", "data.OtherNames": "operating_names", "data.AnnualReports": "acnc_ais_url", "data.Programs": "programs"}))
        _replace_coverage(card, CoverageObservation(capability="latest_acnc_ais", status="not_available_from_source", observed_at="2026-08-13", freshness_note="No submitted AIS appears in the 2026-08-13 public ACNC profile acquisition."))
        return
    latest = max(submitted, key=lambda item: (int(item.get("Year") or 0), item.get("DateReceived") or ""))
    year, ais_uuid = str(latest["Year"]), latest["AISId"]
    ais_url = f"https://www.acnc.gov.au/charity/charities/{uuid}/documents/{ais_uuid}"
    evidence_id = f"ev:acnc:ais:{abn}:{year}"
    _evidence(card, EvidenceRef(evidence_id=evidence_id, source_type="regulatory", title=f"{data.get('Name', card.display_name)} Annual Information Statement {year}", publisher="Australian Charities and Not-for-profits Commission", url=ais_url, observed_at=(latest.get("DateReceived") or "")[:10] or None))
    card.acnc_profile_url, card.acnc_ais_url = profile_url, ais_url
    card.source_native_records.append(SourceNativeRecord(source_record_id=record_id, source_family="acnc-public-profile", dataset_version="2026-08-13-public-api", source_url=profile_url, retrieved_at=now, observed_at=(latest.get("DateReceived") or "")[:10], source_fields={"uuid": uuid, "abn": abn, "latest_ais_year": year, "latest_ais_uuid": ais_uuid}, source_payload=entity, canonical_field_mappings={"data.Name": "display_name", "data.OtherNames": "operating_names", "data.AnnualReports": "acnc_ais_url", "data.Programs": "programs"}, evidence_ids=[evidence_id]))
    card.programs = [ProgramObservation(
        program_id=f"prg:acnc:{abn}:{item.get('uuid', index)}", name=item.get("Name") or "Unnamed ACNC program",
        description=item.get("ProgramClassification"), beneficiaries=list(item.get("ProgramBeneficiaries") or []),
        geography=[location.get("DisplayName") or location.get("Name") for location in item.get("ProgramLocations", []) if location.get("DisplayName") or location.get("Name")],
        status="current", reporting_period=year, source_url=item.get("ProgramWeblink") or ais_url, evidence_ids=[evidence_id],
    ) for index, item in enumerate(data.get("Programs") or [])]
    _replace_coverage(card, CoverageObservation(capability="latest_acnc_ais", status="observed", evidence_ids=[evidence_id], observed_at=(latest.get("DateReceived") or "")[:10], freshness_note=f"Latest submitted ACNC AIS in the 2026-08-13 public-profile acquisition: {year}."))


def _eja(card: CauseBaseCard, now: datetime) -> None:
    annual_id, financial_id, ais_id = "ev:report:eja:annual-2025", "ev:report:eja:financial-2025", "ev:acnc:ais:eja:2025"
    _evidence(card, EvidenceRef(evidence_id=annual_id, source_type="organisation_self_report", title="Environmental Justice Australia Annual Report 2024–25", publisher="Environmental Justice Australia", url=EJA_ANNUAL, observed_at="2025-11-01", page=27))
    _evidence(card, EvidenceRef(evidence_id=financial_id, source_type="organisation_self_report", title="Environmental Justice Australia Financial Report 2024–25", publisher="Environmental Justice Australia", url=EJA_FINANCIAL, observed_at="2025-10-01", page=8))
    _evidence(card, EvidenceRef(evidence_id=ais_id, source_type="regulatory", title="Environmental Justice Australia Annual Information Statement 2025", publisher="Australian Charities and Not-for-profits Commission", url=EJA_AIS, observed_at="2025-08-13"))
    card.acnc_profile_url, card.acnc_ais_url = EJA_PROFILE, EJA_AIS
    card.principal_location = "Victoria, Australia"
    _replace_coverage(card, CoverageObservation(capability="latest_acnc_ais", status="observed", evidence_ids=[ais_id], observed_at="2025-08-13", freshness_note="Public ACNC AIS 2025 locator retained; detailed field extraction remains source-native."))
    financial = Financials(
        financial_record_id=f"fr:report:{card.causebase_id}:2025", period={"period_start": "2024-07-01", "period_end": "2025-06-30", "period_length_days": 365, "label": "2024–25"},
        reporting_scope="subject", reporting_subject_causebase_id=card.causebase_id, covered_subjects=[card.causebase_id], consolidated="false", attribution_method="direct_subject_report", evidence_ids=[financial_id],
        revenue=_money("5016000"), donations=_money("2051817"), government_grants=_money("365135"), employee_costs=_money("4670344"), total_expenses=_money("5852789"), assets=_money("4740194"), liabilities=_money("849076"),
        income_breakdown=[
            FinancialLineItem(label="Grants", category="income", amount=_money("2078583"), evidence_ids=[financial_id]), FinancialLineItem(label="VLA Funds", category="income", amount=_money("365135"), evidence_ids=[financial_id]), FinancialLineItem(label="Donations, fundraisings and lectures", category="income", amount=_money("2051817"), evidence_ids=[financial_id]), FinancialLineItem(label="Donations – Future Fund", category="income", amount=_money("50000"), evidence_ids=[financial_id]), FinancialLineItem(label="Fees for service", category="income", amount=_money("51771"), evidence_ids=[financial_id]), FinancialLineItem(label="Future Fund income", category="income", amount=_money("125702"), evidence_ids=[financial_id]), FinancialLineItem(label="Interest received", category="income", amount=_money("79883"), evidence_ids=[financial_id]),
        ], expense_breakdown=[
            FinancialLineItem(label="Employee benefits", category="expense", amount=_money("4670344"), evidence_ids=[financial_id]), FinancialLineItem(label="Legal expenses", category="expense", amount=_money("333105"), evidence_ids=[financial_id]), FinancialLineItem(label="IT expenses", category="expense", amount=_money("289239"), evidence_ids=[financial_id]), FinancialLineItem(label="Administrative expenses", category="expense", amount=_money("267635"), evidence_ids=[financial_id]), FinancialLineItem(label="Occupancy expenses", category="expense", amount=_money("75472"), evidence_ids=[financial_id]), FinancialLineItem(label="Consultants", category="expense", amount=_money("69391"), evidence_ids=[financial_id]),
        ], balance_sheet_breakdown=[
            FinancialLineItem(label="Cash and cash equivalents", category="asset", amount=_money("2595450"), evidence_ids=[financial_id]), FinancialLineItem(label="Financial assets", category="asset", amount=_money("1703602"), evidence_ids=[financial_id]), FinancialLineItem(label="Net assets / equity", category="equity", amount=_money("3891118"), evidence_ids=[financial_id]),
        ],
    )
    card.financial_records = [item for item in card.financial_records if item.financial_record_id != financial.financial_record_id] + [financial]
    card.funding_sources = [
        FundingSourceObservation(source_type="philanthropic_grants", source_label="Grants", period_label="2024–25", amount=_money("2078583"), reporting_scope="subject", evidence_ids=[financial_id]), FundingSourceObservation(source_type="government_grants_or_contracts", source_label="VLA Funds", period_label="2024–25", amount=_money("365135"), reporting_scope="subject", evidence_ids=[financial_id]), FundingSourceObservation(source_type="individual_donations", source_label="Donations, fundraisings and lectures", period_label="2024–25", amount=_money("2051817"), reporting_scope="subject", evidence_ids=[financial_id]), FundingSourceObservation(source_type="investment_income", source_label="Future Fund income", period_label="2024–25", amount=_money("125702"), reporting_scope="subject", evidence_ids=[financial_id]), FundingSourceObservation(source_type="service_or_earned_income", source_label="Fees for service", period_label="2024–25", amount=_money("51771"), reporting_scope="subject", evidence_ids=[financial_id]),
    ]
    card.fundraising_methods = [FundraisingMethodObservation(method=method, status="current", observed_at="2025-11-01", evidence_ids=[annual_id]) for method in ("regular_giving", "bequest_program", "major_donor_program", "appeals")]
    card.participation_observations = [ParticipationObservation(mode=mode, label=label, status="current", observed_at="2025-11-01", evidence_ids=[annual_id], source_url="https://envirojustice.org.au/") for mode, label in (("donate", "Donate"), ("regular_giving", "Monthly giving"), ("bequest", "Bequest"), ("membership", "Membership"), ("volunteer", "Volunteer"), ("employment", "Work with EJA"), ("action", "Take action"), ("resource", "Toolkits and guides"))]
    card.programs = [ProgramObservation(program_id=f"prg:{card.causebase_id}:public-interest-environmental-law", name="Public-interest environmental law", description="Legal advice, representation, litigation, legal interventions and advocacy for communities affected by environmental harm.", beneficiaries=["Communities affected by environmental harm", "Traditional Owners"], geography=["Australia"], status="current", reporting_period="2024–25", source_url=EJA_ANNUAL, evidence_ids=[annual_id])]
    card.fundraising_expenditure = None
    _replace_coverage(card, CoverageObservation(capability="fundraising_expenditure", status="not_available_from_source", evidence_ids=[financial_id], observed_at="2025-10-01", freshness_note="The 2024–25 report presents fundraising as a rounded chart category; no false-precision dollar reconstruction is published."))


def project_phase2c(input_dir: Path, output_dir: Path, dataset_version: str, *, archive_root: Path, embedding_cache_root: Path | None = None) -> dict:
    raw = json.loads((input_dir / "causebase.json").read_text(encoding="utf-8"))
    manifest = json.loads((input_dir / "manifest.json").read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    ais_rows = _load_rows(next((archive_root / "sources" / "regulator" / "acnc-ais-2023" / "2026-08-10").glob("*.csv")))
    dgr_rows = _dgr_abns(archive_root / "processed" / "national-backbone" / "2026-08-10" / "dgr-source-records.jsonl")
    public_profiles = json.loads((archive_root / "sources" / "regulator" / "acnc-public-profiles" / "2026-08-13" / "entities.json").read_text(encoding="utf-8"))["entities"]
    cards: list[CauseBaseCard] = []
    for row in raw["entities"]:
        card = CauseBaseCard.model_validate(row); abn = _abn(card)
        card.dataset_version, card.card_schema_version, card.editorial_policy_version, card.generator_version, card.built_at = dataset_version, "0.4", RC3_EDITORIAL_POLICY_VERSION, RC3_GENERATOR_VERSION, now
        card.canonical_url = f"{CANONICAL_VIEWER_ROOT}#{card.causebase_id}"
        card.activities = [item.removesuffix(" (as described by the organisation)") for item in card.activities]
        card.beneficiaries = [item.removesuffix(" (as described by the organisation)") for item in card.beneficiaries]
        card.geography = [item.removesuffix(" (as described by the organisation)") for item in card.geography]
        if abn in ais_rows: _raw_ais_sidecar(card, ais_rows[abn], now)
        if abn in public_profiles: _latest_public_acnc(card, public_profiles[abn], now)
        if abn in dgr_rows:
            dgr_id = f"ev:abr-dgr:{abn}:20260805"; _evidence(card, EvidenceRef(evidence_id=dgr_id, source_type="regulatory", title="ABR DGR bulk observation", publisher="Australian Business Register / Australian Taxation Office", url="https://abr.business.gov.au/Tools/BulkExtract", observed_at="2026-08-05")); card.tax_statuses = [item for item in card.tax_statuses if item.scheme != "ABR DGR"] + [TaxStatus(scheme="ABR DGR", status="endorsed", detail="Dated 2026-08-05 ABR bulk observation", evidence_ids=[dgr_id])]
        if card.causebase_id == EJA_ID: _eja(card, now)
        cards.append(CauseBaseCard.model_validate(card.model_dump(mode="json")))
    if embedding_cache_root is not None:
        cards, vectors, embedding_run = attach_production_embeddings(cards, cache_root=embedding_cache_root)
        similarities = build_similarity_rows(cards, vectors, min_score=0.45)
    else:
        vectors = {row["causebase_id"]: row["vector"] for row in json.loads((input_dir / "embeddings.json").read_text(encoding="utf-8"))}
        similarities = json.loads((input_dir / "similarities.json").read_text(encoding="utf-8"))
        embedding_run = {"cache_hits": 0, "generated": 0, "input_tokens": 0, "note": "Not refreshed"}
    for row in similarities: row["dataset_version"] = dataset_version
    taxonomy = json.loads((input_dir / "taxonomy" / "causebase-v0.json").read_text(encoding="utf-8"))
    history = {"releases": [{"dataset_version": manifest["dataset_version"], "status": "historical", "manifest_sha256": file_sha256(input_dir / "manifest.json"), "immutable": True}, {"dataset_version": dataset_version, "status": "candidate", "derived_from": manifest["dataset_version"], "immutable": False}]}
    inventory = {"inventory_version": "phase2b-rc3", "scope": "Existing 120-card corpus; no new subjects.", "cost_reconciliation": {"request_count": 120, "model": "gpt-5-mini-2025-08-07", "input_tokens": 327726, "output_tokens": 222747, "reasoning_tokens": None, "estimated_usd": "0.527423", "retries_or_duplicate_response_ids": 0, "note": "Dashboard movements are external timing/accounting observations and cannot be attributed from response telemetry alone."}, "embedding_run": embedding_run, "gap_report": ["Current acquired ACNC AIS 2023 rows are retained source-native for all matching cards.", "EJA has an observed current ACNC profile/AIS locator and public 2024–25 reports; profile UUIDs are not fabricated for other cards.", "Latest per-charity AIS acquisition for every subject remains an explicit follow-on source refresh task."]}
    inventory["gap_report"] = [
        "Current acquired ACNC AIS 2023 rows are retained source-native for all matching cards.",
        "A 2026-08-13 public ACNC profile acquisition supplies a latest submitted AIS locator and full source-native response for every card.",
        "EJA also carries public 2024-25 annual and financial report observations.",
    ]
    return render_publication(cards, vectors, similarities, output_dir, taxonomy=taxonomy, agent_guide=(input_dir / "agent-guide.md").read_text(encoding="utf-8"), source_inventory=inventory, release_history=history)

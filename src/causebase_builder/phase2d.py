"""RC4 evidence projection for the fixed 120-card corpus.

All enrichment here is keyed by source records (ABN, regulator UUID and
document hash), never by a CauseBase card or organisation name.
"""
from __future__ import annotations

import csv
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .models import CauseBaseCard, ComparativePeriodAmount, CoverageObservation, EvidenceRef, FinancialLineItem, Financials, FinancialStatementObservation, FinancialStatementRow, FundraisingMethodObservation, FundingSourceObservation, MoneyObservation, ParticipationObservation, ProgramObservation, SourceNativeRecord, StructuredValueObservation, TaxStatus
from .render import file_sha256, render_publication

GENERATOR_VERSION = "0.5.0-rc4"
EDITORIAL_POLICY_VERSION = "0.4-rc4"
VIEWER_ROOT = "https://gregorycwhill.github.io/CauseBase-Viewer/"
ACNC = "https://www.acnc.gov.au"


def _abn(card: CauseBaseCard) -> str | None:
    return next((x.value for x in card.external_identifiers if x.scheme.lower() == "abn"), None)


def _money(value: str) -> MoneyObservation:
    raw = value.strip()
    negative = raw.startswith("(") and raw.endswith(")")
    number = raw.strip("()").replace(",", "")
    if negative:
        number = "-" + number
    return MoneyObservation(source_amount=number, normalised_amount=number, source_raw_value=raw)


def _add_evidence(card: CauseBaseCard, evidence: EvidenceRef) -> None:
    if not any(x.evidence_id == evidence.evidence_id for x in card.evidence):
        card.evidence.append(evidence)


def _coverage(card: CauseBaseCard, item: CoverageObservation) -> None:
    card.coverage = [x for x in card.coverage if x.capability != item.capability] + [item]


def _separate_legacy_provenance(values: list[str]) -> tuple[list[str], list[StructuredValueObservation]]:
    """Move a terminal source qualifier into metadata without phrase rewrites.

    This recognises the *shape* of legacy attribution (a terminal parenthetical
    or source-prefixed clause), preserves that qualifier verbatim as metadata,
    and leaves substantive parentheticals untouched.
    """
    clean, observations = [], []
    for original in values:
        value, note = original.strip(), None
        head, marker, tail = value.rpartition(" (")
        if marker and tail.endswith(")"):
            qualifier = tail[:-1].strip()
            if qualifier.casefold().startswith("as ") or any(token in qualifier.casefold() for token in ("website", "site", "organisation")):
                value, note = head.strip(), qualifier
        elif ":" in value:
            prefix, remainder = value.split(":", 1)
            if any(token in prefix.casefold() for token in ("website", "site", "organisation")) and remainder.strip():
                value, note = remainder.strip(), prefix.strip()
        clean.append(value)
        observations.append(StructuredValueObservation(value=value, source_role="legacy_source_qualifier" if note else "unknown", provenance_note=note))
    return clean, observations


def _load_ais_rows(root: Path) -> dict[str, dict[str, str]]:
    source = next((root / "sources" / "regulator" / "acnc-ais-2023" / "2026-08-10").glob("*.csv"))
    with source.open(encoding="utf-8-sig", newline="") as handle:
        return {row["ABN"]: dict(row) for row in csv.DictReader(handle) if row.get("ABN")}


def _dgr_abns(path: Path) -> set[str]:
    rows = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        if item.get("dgr_status") == "endorsed":
            rows.update(x["value"] for x in item.get("external_identifiers", []) if x.get("scheme") == "abn")
    return rows


def _profile_and_detail(source: dict) -> tuple[dict, dict | None, dict | None, str | None]:
    # RC4 acquisition wraps a profile and the separately fetched AIS detail.
    if "profile" in source:
        return source["profile"], source.get("latest_submitted_ais"), source.get("ais_detail"), source.get("ais_acquisition_failure")
    return source, None, None, "pre-RC4 profile artifact has no detail acquisition"


def _acnc(card: CauseBaseCard, source: dict, now: datetime) -> None:
    profile, latest, detail, failure = _profile_and_detail(source)
    data, abn = profile["data"], _abn(card)
    uuid = profile["uuid"]
    profile_url = f"{ACNC}/charity/charities/{uuid}/profile"
    card.acnc_profile_url = profile_url
    card.operating_names = [x.get("Name") if isinstance(x, dict) else str(x) for x in data.get("OtherNames", []) if (x.get("Name") if isinstance(x, dict) else x)]
    card.principal_location = ", ".join(x for x in [data.get("AddressStateOrProvince"), "Australia"] if x)
    profile_id = f"src:acnc-public-profile:{abn}:{uuid}:{card.causebase_id}"
    # A new acquisition supersedes only prior representations of the same
    # regulator record.  Historical raw AIS rows remain append-only.
    card.source_native_records = [x for x in card.source_native_records if not x.source_record_id.startswith(f"src:acnc-public-profile:{abn}:") and not x.source_record_id.startswith(f"src:acnc-ais-detail:{abn}:")]
    observed = date.fromisoformat((latest or {}).get("DateReceived", now.date().isoformat())[:10])
    card.source_native_records.append(SourceNativeRecord(source_record_id=profile_id, source_family="acnc-public-profile", dataset_version="2026-08-14-public-api", source_url=profile_url, retrieved_at=now, observed_at=observed, source_fields={"uuid": uuid, "abn": abn}, source_payload=profile, canonical_field_mappings={"data.OtherNames": "operating_names", "data.AddressStateOrProvince": "principal_location"}))
    if not latest:
        _coverage(card, CoverageObservation(capability="latest_acnc_ais", status="not_available_from_source", source_record_id=profile_id, observed_at=now.date(), freshness_note="No submitted AIS was returned by the public ACNC profile endpoint."))
        return
    year, ais_uuid = str(latest["Year"]), latest["AISId"]
    ais_url = f"{ACNC}/charity/charities/{uuid}/documents/{ais_uuid}"
    evidence_id = f"ev:acnc:ais:{abn}:{ais_uuid}"
    _add_evidence(card, EvidenceRef(evidence_id=evidence_id, source_type="regulatory", title=f"ACNC Annual Information Statement {year}", publisher="Australian Charities and Not-for-profits Commission", url=ais_url, observed_at=observed, reporting_period=year))
    card.acnc_ais_url = ais_url
    detail_id = f"src:acnc-ais-detail:{abn}:{ais_uuid}:{card.causebase_id}"
    if detail:
        payload = detail.get("data", {})
        card.source_native_records.append(SourceNativeRecord(source_record_id=detail_id, source_family="acnc-ais-detail", dataset_version="2026-08-14-public-api", source_url=ais_url, retrieved_at=now, observed_at=observed, source_fields={"abn": abn, "ais_uuid": ais_uuid, "year": year, "date_received": latest.get("DateReceived")}, source_payload=detail, canonical_field_mappings={"data.Programs": "programs", "data.TotalRevenue": "financial_records[].revenue", "data.TotalExpenses": "financial_records[].total_expenses"}, evidence_ids=[evidence_id]))
        programs = []
        for index, item in enumerate(payload.get("Programs") or []):
            name = item.get("Name") or item.get("ProgramName")
            if not name:
                continue
            programs.append(ProgramObservation(program_id=f"prg:acnc:{abn}:{item.get('uuid', index)}", name=name, description=item.get("ProgramClassification"), beneficiaries=list(item.get("ProgramBeneficiaries") or []), geography=[location.get("DisplayName") or location.get("Name") for location in item.get("ProgramLocations", []) if location.get("DisplayName") or location.get("Name")], status="current", reporting_period=year, source_url=item.get("ProgramWeblink") or ais_url, evidence_ids=[evidence_id]))
        # Never discard AIS programs when later report observations are added.
        existing = {(x.name.casefold(), x.reporting_period) for x in card.programs}
        card.programs += [x for x in programs if (x.name.casefold(), x.reporting_period) not in existing]
        _coverage(card, CoverageObservation(capability="latest_acnc_ais", status="observed", source_record_id=detail_id, evidence_ids=[evidence_id], observed_at=observed, freshness_note="Latest submitted AIS detail acquired from the public ACNC entity endpoint."))
    else:
        card.source_native_records.append(SourceNativeRecord(source_record_id=detail_id, source_family="acnc-ais-detail", dataset_version="2026-08-14-public-api", source_url=ais_url, retrieved_at=now, observed_at=observed, source_fields={"abn": abn, "ais_uuid": ais_uuid, "year": year, "acquisition_failure": failure}, canonical_field_mappings={}, evidence_ids=[evidence_id]))
        _coverage(card, CoverageObservation(capability="latest_acnc_ais", status="retrieval_failed", source_record_id=detail_id, evidence_ids=[evidence_id], observed_at=observed, freshness_note=f"AIS detail retrieval failed: {failure or 'unspecified error'}"))


LINE = re.compile(r"^(?P<label>.+?)\s+(?P<current>\(?[\d,]+\)?)\s+(?P<comparative>\(?[\d,]+\)?)$")
BARE_PAIR = re.compile(r"^(?P<current>\(?[\d,]+\)?)\s+(?P<comparative>\(?[\d,]+\)?)$")
KEYS = (("total assets", "assets", "asset"), ("total liabilities", "liabilities", "liability"), ("net assets", "net_assets", "equity"), ("total expenses", "total_expenses", "expense"), ("employee benefits", "employee_costs", "expense"), ("total income", "revenue", "income"), ("revenue", "revenue", "income"))


def _report_rows(extract: dict) -> list[dict]:
    """Return only rows in the two primary statements, in printed order.

    A canonical metric is deliberately *not* used to decide which row enters
    this result.  It is added later as an annotation.
    """
    rows = []
    statement, statement_title = None, None
    candidate_statement, candidate_title, candidate_page = None, None, None
    for page in extract.get("pages", []):
        printed_page = next((line.strip() for line in reversed(page.get("text", "").splitlines()) if line.strip().isdigit()), None)
        section_hint = None
        for line in page.get("text", "").splitlines():
            lowered = line.casefold()
            # Stop before notes/disclosures: they commonly mention a statement
            # by name but are not themselves primary statement rows.
            if lowered.startswith("the above statement") or "accompanying notes" in lowered:
                statement, candidate_statement, candidate_title, candidate_page = None, None, None, None
            elif lowered.startswith("statement of profit or loss") or lowered.startswith("statement of comprehensive income") or lowered.startswith("income statement"):
                candidate_statement, candidate_title, candidate_page, statement = "profit_and_loss", line.strip(), page["page"], None
            elif lowered.startswith("statement of financial position") or lowered.startswith("balance sheet"):
                candidate_statement, candidate_title, candidate_page, statement = "financial_position", line.strip(), page["page"], None
            elif lowered.startswith("statement of cash flows"):
                candidate_statement, candidate_title, candidate_page, statement = "cash_flow", line.strip(), page["page"], None
            elif lowered.startswith("statement of changes in equity"):
                candidate_statement, candidate_title, candidate_page, statement = "changes_in_equity", line.strip(), page["page"], None
            elif candidate_statement and candidate_page == page["page"] and ("for the year ended" in lowered or lowered.startswith("as at ")):
                statement, statement_title = candidate_statement, candidate_title
            match = LINE.match(line.strip())
            bare_pair = BARE_PAIR.match(line.strip())
            if statement and line.strip() and not re.fullmatch(r"\d+", line.strip()):
                if match:
                    values = match.groupdict()
                elif bare_pair:
                    # Some statements print a subtotal with no repeated label.
                    # Keep the exact raw row while retaining both amounts.
                    values = {"label": line.strip(), **bare_pair.groupdict(), "unlabelled_numeric_row": True, "section_hint": section_hint}
                else:
                    values = {"label": line.strip(), "current": None, "comparative": None}
                    if line.strip().casefold() in {"revenue", "income"}: section_hint = "revenue"
                    elif line.strip().casefold() in {"expenses", "expenditure"}: section_hint = "total_expenses"
                rows.append({"page": page["page"], "printed_page": printed_page, "statement": statement, "statement_title": statement_title, "indent": len(line) - len(line.lstrip()), "source_location": f"PDF page {page['page']}, text row {len(rows) + 1}", **values})
    return rows


def _statements(rows: list[dict], evidence_id: str, period: dict) -> list[FinancialStatementObservation]:
    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        grouped.setdefault((row["statement"], row["statement_title"] or row["statement"]), []).append(row)
    result = []
    for (statement_type, title), source_rows in grouped.items():
        statement_rows = []
        for index, row in enumerate(source_rows):
            label, lower = row["label"], row["label"].casefold()
            row_type = "heading" if not row.get("current") else "total" if lower.startswith("total ") else "subtotal" if label.isupper() or label.endswith(":") else "line_item"
            mappings = [target for needle, target, _ in KEYS if needle in lower] or ([row["section_hint"]] if row.get("unlabelled_numeric_row") and row.get("section_hint") else [])
            statement_rows.append(FinancialStatementRow(source_label=label, source_order=index, row_type=row_type, hierarchy_indent=row["indent"], current_amount=_money(row["current"]) if row.get("current") else None, comparative_periods=[ComparativePeriodAmount(amount=_money(row["comparative"]))] if row.get("comparative") else [], page=row["page"], source_location=row["source_location"], extraction_method="native_text_and_tables", extraction_confidence="high" if row.get("current") else "medium", extraction_warnings=[], evidence_ids=[evidence_id], canonical_metrics=mappings))
        result.append(FinancialStatementObservation(statement_type=statement_type, statement_title=title, source_document_evidence_id=evidence_id, reporting_scope="subject", period=period, rows=statement_rows))
    return result


def _category(label: str) -> str:
    value = label.casefold()
    if any(word in value for word in ("asset", "cash", "receivable")): return "asset"
    if any(word in value for word in ("liabilit", "payable", "provision")): return "liability"
    if any(word in value for word in ("expense", "depreciation", "amortisation", "occupancy", "consultant", "employee", "travel", "administrative", "legal")): return "expense"
    if "equity" in value or "net assets" in value: return "equity"
    return "income"


def _report_locator(extract: dict, locators: list[dict]) -> dict | None:
    filename = extract.get("filename", "").casefold()
    year_tokens = set(re.findall(r"20\d{2}", filename))
    preferred_type = "Annual Report" if "annual" in filename else "Financial Report" if "financial" in filename else None
    candidates = [x for x in locators if not preferred_type or x.get("type") == preferred_type]
    by_year = [x for x in candidates if year_tokens & set(re.findall(r"20\d{2}", f"{x.get('title', '')} {x.get('year', '')}"))]
    # When a filename spans two years, prefer the most recent matching
    # regulator document rather than the first historical profile entry.
    return sorted(by_year or candidates, key=lambda item: (item.get("year") or "", item.get("published_at") or ""), reverse=True)[0] if (by_year or candidates) else None


def _report_period(extract: dict) -> dict:
    text = "\n".join(page.get("text", "") for page in extract.get("pages", []))
    match = re.search(r"(?:for the year ended|year ended)\s+(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})", text, re.I)
    if not match:
        return {"label": "Report period not reliably parsed"}
    day, month, year = match.groups()
    end = datetime.strptime(f"{day} {month} {year}", "%d %B %Y").date()
    return {"period_start": end - timedelta(days=364), "period_end": end, "period_length_days": 365, "label": f"year ended {end.isoformat()}"}


def _reports(card: CauseBaseCard, extracts: list[dict], locators: list[dict], now: datetime) -> None:
    abn = _abn(card)
    for extract in extracts:
        rows = _report_rows(extract)
        evidence_id = f"ev:report:{abn}:{extract['source_sha256'][:16]}"
        observed = now.date()
        title = extract.get("filename", "Organisation report")
        locator = _report_locator(extract, locators)
        source_url = locator.get("url") if locator else None
        document_type = (locator or {}).get("type") or ("Annual Report" if "annual" in title.casefold() else "Financial Report" if "financial" in title.casefold() else "Report")
        report_page = next((int(row["printed_page"]) for row in rows if row.get("printed_page")), None)
        _add_evidence(card, EvidenceRef(evidence_id=evidence_id, source_type="organisation_self_report", title=title, publisher=card.display_name, url=source_url, observed_at=observed, reporting_period=(locator or {}).get("year"), page=report_page))
        record_id = f"src:report-extract:{abn}:{extract['source_sha256'][:16]}:{card.causebase_id}"
        card.source_native_records = [x for x in card.source_native_records if x.source_record_id != record_id]
        card.source_native_records.append(SourceNativeRecord(source_record_id=record_id, source_family="organisation-report-extract", dataset_version="2026-08-14-private-extraction", source_url=source_url, retrieved_at=now, observed_at=observed, source_fields={"filename": title, "source_sha256": extract["source_sha256"], "page_count": extract.get("page_count"), "discovery_basis": "ACNC public profile Documents field"}, source_payload={"rows": rows, "diagnostics": extract.get("extraction_diagnostics", {})}, canonical_field_mappings={"rows[].label": "financial_records[].*_breakdown", "rows[].current": "financial_records[].*_breakdown[].amount"}, evidence_ids=[evidence_id]))
        # Preserve a report's fundraising signal without inferring a channel or
        # an amount where the source does not state one.
        fundraising_pages = [page["page"] for page in extract.get("pages", []) if "fundrais" in page.get("text", "").casefold()]
        if fundraising_pages:
            card.fundraising_methods.append(FundraisingMethodObservation(method="other", status="current", observed_at=observed, evidence_ids=[evidence_id]))
        # Evidence-derived participation observations use the report as their
        # public source when a more specific public participation page has not
        # been acquired.  No organisation-specific labels or URLs are used.
        report_text = "\n".join(page.get("text", "") for page in extract.get("pages", []))
        participation_terms = (("bequest", "gift in a will", "Will"), ("membership", "member", "Membership"), ("volunteer", "volunteer", "Volunteer"), ("donate", "donor", "Donate"))
        known = {(item.mode, tuple(item.evidence_ids)) for item in card.participation_observations}
        for mode, marker, label in participation_terms:
            if marker.casefold() in report_text.casefold() and (mode, (evidence_id,)) not in known:
                card.participation_observations.append(ParticipationObservation(mode=mode, label=label, status="current", observed_at=observed, source_url=source_url, evidence_ids=[evidence_id]))
        if document_type == "Annual Report":
            _coverage(card, CoverageObservation(capability="annual_report", status="observed", source_record_id=record_id, evidence_ids=[evidence_id], observed_at=observed, freshness_note="Annual report processed through the generic report extractor."))
        if document_type == "Financial Report":
            _coverage(card, CoverageObservation(capability="financials", status="observed", source_record_id=record_id, evidence_ids=[evidence_id], observed_at=observed, freshness_note="Financial report processed through the generic report extractor."))
        if fundraising_pages and card.fundraising_expenditure is None:
            _coverage(card, CoverageObservation(capability="fundraising_expenditure", status="not_available_from_source", source_record_id=record_id, evidence_ids=[evidence_id], observed_at=observed, freshness_note="Relevant report pages were processed; no direct fundraising-expenditure amount was recovered."))
        if not rows:
            continue
        metrics = {}
        for row in rows:
            if not row.get("current"):
                continue
            lowered = row["label"].casefold()
            for needle, target, _ in KEYS:
                if needle in lowered:
                    metrics[target] = _money(row["current"])
            if row.get("unlabelled_numeric_row") and row.get("section_hint"):
                metrics[row["section_hint"]] = _money(row["current"])
        period = _report_period(extract)
        statements = _statements(rows, evidence_id, period)
        items = [FinancialLineItem(label=row["label"], category=_category(row["label"]), amount=_money(row["current"]), comparative_amount=_money(row["comparative"]), evidence_ids=[evidence_id], note=f"PDF page {row['page']}; printed page {row.get('printed_page') or 'not detected'}", source_statement="income_statement" if row["statement"] == "profit_and_loss" else "financial_position" if row["statement"] == "financial_position" else "other", source_order=index, canonical_metrics=[target for needle, target, _ in KEYS if needle in row["label"].casefold()] or ([row["section_hint"]] if row.get("unlabelled_numeric_row") and row.get("section_hint") else [])) for index, row in enumerate(rows) if row.get("current")]
        financial_id = f"fr:report:{abn}:{extract['source_sha256'][:16]}"
        financial = Financials(financial_record_id=financial_id, period=period, reporting_scope="subject", reporting_subject_causebase_id=card.causebase_id, covered_subjects=[card.causebase_id], consolidated="unknown", attribution_method="direct_subject_report", evidence_ids=[evidence_id], revenue=metrics.get("revenue"), employee_costs=metrics.get("employee_costs"), total_expenses=metrics.get("total_expenses"), assets=metrics.get("assets"), liabilities=metrics.get("liabilities"), net_assets=metrics.get("net_assets"), income_breakdown=[x for x in items if x.source_statement == "income_statement" and x.category == "income"], expense_breakdown=[x for x in items if x.source_statement == "income_statement" and x.category == "expense"], balance_sheet_breakdown=[x for x in items if x.source_statement == "financial_position"], source_ordered_line_items=items, statements=statements)
        card.financial_records = [x for x in card.financial_records if x.financial_record_id != financial_id] + [financial]
        for item in items:
            label = item.label.casefold()
            if "donation" in label and "fundrais" in label:
                # Mixed labels are retained source-native; they are not treated as donations alone.
                source_type = "other"
            elif "grant" in label:
                source_type = "government_grants_or_contracts"
            elif "fee" in label:
                source_type = "service_or_earned_income"
            else:
                continue
            card.funding_sources.append(FundingSourceObservation(source_type=source_type, source_label=item.label, amount=item.amount, reporting_scope="subject", evidence_ids=[evidence_id]))


def project_phase2d(input_dir: Path, output_dir: Path, dataset_version: str, *, archive_root: Path, embedding_cache_root: Path | None = None) -> dict:
    raw = json.loads((input_dir / "causebase.json").read_text(encoding="utf-8"))
    manifest = json.loads((input_dir / "manifest.json").read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    profiles = json.loads((archive_root / "sources" / "regulator" / "acnc-public-profiles" / "2026-08-14" / "entities.json").read_text(encoding="utf-8"))["entities"]
    discovery = json.loads((archive_root / "processed" / "phase2b" / "2026-08-14" / "source-discovery.json").read_text(encoding="utf-8"))["entities"]
    ais_rows = _load_ais_rows(archive_root)
    dgr = _dgr_abns(archive_root / "processed" / "national-backbone" / "2026-08-10" / "dgr-source-records.jsonl")
    reports_by_abn: dict[str, list[dict]] = {}
    for path in (archive_root / "processed" / "phase2b" / "2026-08-14" / "report-extracts").glob("*.json"):
        if path.name == "manifest.json": continue
        item = json.loads(path.read_text(encoding="utf-8")); reports_by_abn.setdefault(item["abn"], []).append(item)
    cards = []
    for row in raw["entities"]:
        card = CauseBaseCard.model_validate(row); abn = _abn(card)
        card.dataset_version, card.card_schema_version, card.editorial_policy_version, card.generator_version, card.built_at = dataset_version, "0.4", EDITORIAL_POLICY_VERSION, GENERATOR_VERSION, now
        card.canonical_url = f"{VIEWER_ROOT}#{card.causebase_id}"
        card.activities, card.activity_observations = _separate_legacy_provenance(card.activities)
        card.beneficiaries, card.beneficiary_observations = _separate_legacy_provenance(card.beneficiaries)
        card.geography, card.geography_observations = _separate_legacy_provenance(card.geography)
        if abn in ais_rows:
            legacy_id = f"src:acnc-ais-full:{abn}:2023"
            card.source_native_records = [x for x in card.source_native_records if x.source_record_id != legacy_id]
            card.source_native_records.append(SourceNativeRecord(source_record_id=legacy_id, source_family="acnc-ais", dataset_version="2023-acquired-full-row", source_url=f"{ACNC}/charity/about-charity-register/download-charity-register-data", retrieved_at=now, observed_at=date(2026, 8, 10), source_fields={k: v or None for k, v in ais_rows[abn].items()}, canonical_field_mappings={}))
        if abn in profiles: _acnc(card, profiles[abn], now)
        if abn in dgr:
            eid = f"ev:abr-dgr:{abn}:20260805"; _add_evidence(card, EvidenceRef(evidence_id=eid, source_type="regulatory", title="ABR DGR bulk observation", publisher="Australian Business Register / Australian Taxation Office", url="https://abr.business.gov.au/Tools/BulkExtract", observed_at=date(2026, 8, 5))); card.tax_statuses = [x for x in card.tax_statuses if x.scheme != "ABR DGR"] + [TaxStatus(scheme="ABR DGR", status="endorsed", detail="Dated 2026-08-05 ABR bulk observation", evidence_ids=[eid])]
        if discovery.get(abn, {}).get("website"):
            card.website = discovery[abn]["website"]
            _coverage(card, CoverageObservation(capability="website", status="observed", observed_at=now.date(), freshness_note="Public website locator acquired from the ACNC profile."))
        _reports(card, reports_by_abn.get(abn, []), discovery.get(abn, {}).get("reports", []), now)
        cards.append(CauseBaseCard.model_validate(card.model_dump(mode="json")))
    vectors = {row["causebase_id"]: row["vector"] for row in json.loads((input_dir / "embeddings.json").read_text(encoding="utf-8"))}
    similarities = json.loads((input_dir / "similarities.json").read_text(encoding="utf-8"))
    for row in similarities: row["dataset_version"] = dataset_version
    taxonomy = json.loads((input_dir / "taxonomy" / "causebase-v0.json").read_text(encoding="utf-8"))
    history = {"releases": [{"dataset_version": manifest["dataset_version"], "status": "historical", "manifest_sha256": file_sha256(input_dir / "manifest.json"), "immutable": True}, {"dataset_version": dataset_version, "status": "candidate", "derived_from": manifest["dataset_version"], "immutable": False}]}
    inventory = {"inventory_version": "phase2b-rc4", "scope": "Existing 120-card corpus; no new subjects.", "embedding_run": {"cache_hits": 120, "generated": 0, "input_tokens": 0, "note": "RC3 vectors intentionally reused; source text and summaries were not rewritten."}, "gap_report": ["Public ACNC profile and latest AIS-detail acquisition attempted for all 120 existing subjects.", "AIS detail failures are explicit coverage observations; no profile metadata is substituted for a detail payload.", "Seven already-acquired reports were processed through one deterministic extractor; document URLs are only published where preserved in source acquisition metadata."]}
    return render_publication(cards, vectors, similarities, output_dir, taxonomy=taxonomy, agent_guide=(input_dir / "agent-guide.md").read_text(encoding="utf-8"), source_inventory=inventory, release_history=history)

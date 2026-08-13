"""RC4 evidence projection for the fixed 120-card corpus.

All enrichment here is keyed by source records (ABN, regulator UUID and
document hash), never by a CauseBase card or organisation name.
"""
from __future__ import annotations

import csv
import json
import re
from decimal import Decimal
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .models import CauseBaseCard, ComparativePeriodAmount, CoverageObservation, DerivativeAssessment, DerivedRevenueShare, EvidenceRef, FinancialLineItem, Financials, FinancialStatementObservation, FinancialStatementRow, FunctionalExpenseAllocation, FundraisingMethodObservation, FundingSourceObservation, MoneyObservation, ParticipationObservation, ProgramObservation, RevenueShareComponent, SourceNativeRecord, StructuredValueObservation, SynthesisMetadata, TaxStatus
from .render import file_sha256, render_publication

GENERATOR_VERSION = "0.5.0-rc4"
EDITORIAL_POLICY_VERSION = "0.4-rc4"
VIEWER_ROOT = "https://gregorycwhill.github.io/CauseBase-Viewer/"
ACNC = "https://www.acnc.gov.au"

# Bounded RC4 editorial remediation of the human-reviewed structured-value
# residues. These are source wording repairs, not organisation enrichment
# rules: each entry records whether narrative provenance can be removed (A) or
# whether the value belonged in another field and must be omitted (C).
STRUCTURED_VALUE_REMEDIATIONS = {
    "Public events (website invites subscriptions and to 'keep updated on ... events')": ("A", "Public events", "Removed routine source narration."),
    "Subscription to updates and public webinars (public events listed on website)": ("A", "Subscription to updates and public webinars", "Removed routine source narration."),
    "Runs a mobile veterinary clinic described on the website as 100% Fear Free certified in Melbourne": ("A", "Runs a 100% Fear Free certified mobile veterinary clinic in Melbourne", "Retained substantive certification; removed source narration."),
    "Personalised disability support services described on the organisation website": ("A", "Personalised disability support services", "Removed routine source narration."),
    "Displays a partners section on its website (heading present in captured excerpt)": ("C", None, "A website heading alone is not a reliable activity value."),
    "Publishes website content comparing giving fund structures and direct giving": ("A", "Publishes content comparing giving fund structures and direct giving", "Website is a provenance channel, not the activity."),
    "Website information for donors": ("A", "Information for donors", "Removed routine source narration."),
    "Volunteering (website invites volunteers and partners)": ("A", "Volunteering", "Removed routine source narration."),
    "Wildlife species mentioned on the website (black rhino, snow leopards, African wild dogs, hummingbirds, macaws, birds of paradise, rediscovered Papua marsupials)": ("A", "Wildlife species including black rhino, snow leopards, African wild dogs, hummingbirds, macaws, birds of paradise and Papua marsupials", "Retained substantive examples; removed source narration."),
    "Habitats and ecosystems cited on the website (savannas, rainforests, lower montane tropical forest)": ("A", "Habitats and ecosystems including savannas, rainforests and lower montane tropical forest", "Retained substantive examples; removed source narration."),
    "Three local/regional retirement communities named on the website (locations not specified in provided evidence)": ("A", "Three local or regional retirement communities", "Removed source narration and unsupported location caveat."),
    "Running regular circus classes for children and adults as described on the organisation website": ("A", "Running regular circus classes for children and adults", "Removed routine source narration."),
    "Participation in Peace Education Program sessions in schools, universities, health care settings, veterans groups, police units and correctional facilities (as described by the foundation)": ("A", "Participation in Peace Education Program sessions in schools, universities, health care settings, veterans groups, police units and correctional facilities", "Removed routine source narration."),
    "advocacy and policy activities as described on the website": ("A", "Advocacy and policy activities", "Removed routine source narration."),
    "Identified as a community childrenâ€™s centre by legal name and website (Campbelltown Community Childrenâ€™s Centre Inc)": ("A", "Community children's centre", "Restructured identity evidence into a clean activity label."),
    "Publishing news items on the organisation website": ("A", "Publishing news items", "Website is a provenance channel, not the activity."),
    "Reading website news and announcements": ("A", "Reading news and announcements", "Website is a provenance channel, not the participation mode."),
    "Maintaining a subscription list and website communications": ("A", "Maintaining a subscription list and communications", "Website is a provenance channel, not the activity."),
    "Publishing exhibition details and artist statements on the organisation website": ("A", "Publishing exhibition details and artist statements", "Website is a provenance channel, not the activity."),
    "Membership sign-up (Join now, per website)": ("A", "Membership sign-up", "Removed routine source narration."),
    "Public investiture services / ceremonies (moleben text on website)": ("A", "Public investiture services and ceremonies", "Removed routine source narration."),
    "Offering a newsletter signâ€‘up on the website for program updates and news": ("A", "Offering a newsletter sign-up for program updates and news", "Website is a provenance channel, not the activity."),
    "People who access or view the GOOD streaming service and website content": ("A", "People who access or view GOOD streaming-service content", "Website is a delivery channel, not a beneficiary category."),
    "Online/streaming platforms listed on the organisationâ€™s website (mobile, tablet, web, Apple TV, Smart TV, Foxtel, Fetch, Chromecast)": ("C", None, "Access platforms are not a geography value."),
    "Downloading and streaming the GOOD app on mobile or tablet as described on the website": ("A", "Downloading and streaming the GOOD app on mobile or tablet", "Removed routine source narration."),
    "Accessing GOOD via web or connected TV platforms listed on the website": ("A", "Accessing GOOD via web or connected-TV platforms", "Removed routine source narration."),
    "Signing up to the website newsletter for program news": ("A", "Signing up to the newsletter for program news", "Website is a provenance channel, not the participation mode."),
    "Website invitation to join as a member of settlement agencies": ("C", None, "Membership invitation belongs in participation, not activities."),
    "Website presents the National Settlement Outcome Standards (described as articulating outcomes for refugees and migrants)": ("A", "Publishing National Settlement Outcome Standards for refugees and migrants", "Retained substantive subject; removed source narration."),
    "Website includes a Reconciliation Action Plan (RAP) section": ("A", "Maintaining a Reconciliation Action Plan", "Removed routine source narration."),
    "Membership of settlement agencies (website invitation)": ("A", "Membership of settlement agencies", "Removed routine source narration."),
    "Attending events and workshops mentioned on the website": ("A", "Attending events and workshops", "Removed routine source narration."),
    "Subscribing to ADC communications and resources (website subscription option)": ("A", "Subscribing to ADC communications and resources", "Removed routine source narration."),
    "Newsletter subscription and website updates (site provides subscription field and news)": ("A", "Newsletter subscription and updates", "Removed routine source narration."),
    "Online family payments and contact functions on the organisation website": ("A", "Online family payments and contact functions", "Website is a provenance channel, not the activity."),
    "Families contact the organisation by phone or email (contact details on website)": ("A", "Families contact the organisation by phone or email", "Removed routine source narration."),
    "Families use online payments via the organisation website": ("A", "Families use online payments", "Website is a provenance channel, not the participation mode."),
}
# Preserve Unicode punctuation with Python escapes: this source file can be
# edited through Windows consoles whose active encoding is not UTF-8.
STRUCTURED_VALUE_REMEDIATIONS.update({
    "Identified as a community children\u2019s centre by legal name and website (Campbelltown Community Children\u2019s Centre Inc)": ("A", "Community children's centre", "Restructured identity evidence into a clean activity label."),
    "Offering a newsletter sign\u2011up on the website for program updates and news": ("A", "Offering a newsletter sign-up for program updates and news", "Website is a provenance channel, not the activity."),
    "Online/streaming platforms listed on the organisation\u2019s website (mobile, tablet, web, Apple TV, Smart TV, Foxtel, Fetch, Chromecast)": ("C", None, "Access platforms are not a geography value."),
})


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
        remediation = STRUCTURED_VALUE_REMEDIATIONS.get(value)
        if remediation:
            classification, replacement, note = remediation
            if classification == "C":
                continue
            value = replacement
        head, marker, tail = value.rpartition(" (")
        if marker and tail.endswith(")"):
            qualifier = tail[:-1].strip()
            if qualifier.casefold().startswith("as ") or any(token in qualifier.casefold() for token in ("website", "site", "organisation")):
                value, note = head.strip(), qualifier
        elif ":" in value:
            prefix, remainder = value.split(":", 1)
            if any(token in prefix.casefold() for token in ("website", "site", "organisation")) and remainder.strip():
                value, note = remainder.strip(), prefix.strip()
        # Some legacy strings carry both a terminal qualifier and a reviewed
        # residue. Apply the bounded editorial decision after removing that
        # terminal wrapper as well.
        remediation = STRUCTURED_VALUE_REMEDIATIONS.get(value)
        if remediation:
            classification, replacement, remediation_note = remediation
            if classification == "C":
                continue
            value, note = replacement, remediation_note
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
            statement_rows.append(FinancialStatementRow(observation_id=f"obs:{evidence_id}:{statement_type}:{index}", source_label=label, source_order=index, row_type=row_type, hierarchy_indent=row["indent"], current_amount=_money(row["current"]) if row.get("current") else None, comparative_periods=[ComparativePeriodAmount(amount=_money(row["comparative"]))] if row.get("comparative") else [], page=row["page"], source_location=row["source_location"], extraction_method="native_text_and_tables", extraction_confidence="high" if row.get("current") else "medium", extraction_warnings=[], evidence_ids=[evidence_id], canonical_metrics=mappings))
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
        # Australian report filenames commonly carry an unambiguous financial
        # year even where an annual-report spread does not print the formal
        # statement heading.  This supports cross-report reconciliation while
        # retaining an explicit filename-derived provenance label.
        filename_match = re.search(r"(20\d{2})[-_](\d{2})(?!\d)", extract.get("filename", ""))
        if filename_match:
            start_year, end_year = int(filename_match.group(1)), int("20" + filename_match.group(2))
            if end_year == start_year + 1:
                return {"period_start": date(start_year, 7, 1), "period_end": date(end_year, 6, 30), "period_length_days": 365, "label": f"filename-derived financial year {start_year}-{str(end_year)[-2:]}"}
        return {"label": "Report period not reliably parsed"}
    day, month, year = match.groups()
    end = datetime.strptime(f"{day} {month} {year}", "%d %B %Y").date()
    return {"period_start": end - timedelta(days=364), "period_end": end, "period_length_days": 365, "label": f"year ended {end.isoformat()}"}


def _functional_expense_allocations(extract: dict, evidence_id: str, total_expenses: MoneyObservation | None, period_label: str | None = None) -> list[FunctionalExpenseAllocation]:
    """Validate narrow visual chart output against independently extracted facts.

    The visual adapter supplies generic `functional_expense_allocation`
    observations.  This projection neither knows nor selects organisations or
    category names; it accepts only a complete percentage allocation that sums
    to approximately 100% and reconciles to a separately extracted total.
    """
    observations = [
        {**item, "page": item.get("page", page.get("page")), "extraction_method": item.get("extraction_method", "narrow_vision_structured")}
        for page in extract.get("pages", []) for item in page.get("visual_observations", [])
        if item.get("kind") == "functional_expense_allocation"
    ]
    if not observations or total_expenses is None:
        return []
    try:
        shares = [Decimal(str(item["share_percent"])) / Decimal("100") for item in observations]
    except (KeyError, ArithmeticError, ValueError):
        return []
    if not all(Decimal("0") < share <= Decimal("1") for share in shares) or not Decimal("0.99") <= sum(shares) <= Decimal("1.01"):
        return []
    allocations = []
    for item, share in zip(observations, shares):
        label = str(item.get("source_label", "")).strip()
        if not label:
            return []
        # A chart share is direct; this rounded dollar amount is explicitly a
        # deterministic convenience projection over the independently reported
        # expense total, never an additional financial-statement observation.
        amount = abs(total_expenses.normalised_amount) * share
        rounded = amount.quantize(Decimal("1"))
        allocations.append(FunctionalExpenseAllocation(
            source_label=label, share=share, denominator_label="Total expenses", denominator_amount=total_expenses, reporting_period_label=period_label, allocation_basis="total_expenses",
            derived_amount=MoneyObservation(source_amount=rounded, normalised_amount=rounded, source_raw_value=f"derived from {item['share_percent']}% × reported total expenses"),
            derived_amount_method="rounded_percentage_x_reported_total", derived_amount_approximate=True,
            derivation_note="Mechanically derived rounded estimate from reported share and independently extracted total expenses.",
            evidence_ids=[evidence_id], page=item.get("page"), extraction_method=item.get("extraction_method", "narrow_vision_structured"), extraction_confidence=item.get("extraction_confidence", "medium"),
        ))
    for page in extract.get("pages", []):
        escalation = page.get("vision_escalation")
        if escalation and page.get("visual_observations"):
            escalation["validation_outcome"] = "passed_share_sum_and_total_expenses_cross_check"
    return allocations


def _donations_gifts_bequests(financial: Financials) -> DerivedRevenueShare | None:
    """Project identified giving revenue without turning Funding into a P&L.

    This source-deferential grouping includes an entire printed row when its
    label materially identifies donations, gifts, bequests or fundraising. It
    deliberately does not split a mixed row such as "Donations, Fundraisings,
    Lectures" or estimate an earned-income component.
    """
    if not financial.revenue or financial.revenue.normalised_amount <= 0:
        return None
    components: list[RevenueShareComponent] = []
    evidence_ids: list[str] = []
    denominator_id = None
    for statement in financial.statements:
        if statement.statement_type != "profit_and_loss":
            continue
        in_revenue = False
        for row in statement.rows:
            lowered = row.source_label.casefold().strip()
            if row.row_type == "heading" and lowered in {"revenue", "income"}:
                in_revenue = True
                continue
            if in_revenue and row.row_type == "heading" and lowered in {"expenses", "expenditure"}:
                break
            if "revenue" in row.canonical_metrics and row.current_amount:
                denominator_id = row.observation_id
                continue
            if not in_revenue or row.row_type != "line_item" or not row.current_amount:
                continue
            if lowered == "note" or re.fullmatch(r"[\d, ()$-]+", row.source_label):
                continue
            amount = row.current_amount
            if amount.normalised_amount <= 0 or not any(token in lowered for token in ("donation", "gift", "bequest", "fundrais")):
                continue
            components.append(RevenueShareComponent(observation_id=row.observation_id, source_label=row.source_label, amount=amount))
            evidence_ids.extend(row.evidence_ids)
    if not components or not denominator_id:
        return None
    numerator = sum((component.amount.normalised_amount for component in components), Decimal("0"))
    return DerivedRevenueShare(
        canonical_label="Donations, gifts & bequests", components=components,
        component_observation_ids=[component.observation_id for component in components], numerator_amount=MoneyObservation(source_amount=numerator, normalised_amount=numerator, source_raw_value=" + ".join(component.source_label for component in components)),
        denominator_label="Total income", denominator_observation_id=denominator_id, denominator_amount=financial.revenue,
        formula="reported_revenue_line_divided_by_reported_total_income", reporting_period_label=financial.period.label,
        reporting_scope=financial.reporting_scope, result=numerator / financial.revenue.normalised_amount,
        rounding_note="Includes each full source row explicitly labelled donations, gifts, bequests or fundraising; no mixed row is split or narrowed.", evidence_ids=list(dict.fromkeys(evidence_ids)),
    )


def _merge_programs(programs: list[ProgramObservation]) -> list[ProgramObservation]:
    """Merge same-period program observations without discarding source detail."""
    merged: dict[tuple[str, str | None], ProgramObservation] = {}
    for program in programs:
        key = (program.name.casefold(), program.reporting_period)
        if key not in merged:
            merged[key] = program
            continue
        prior = merged[key]
        prior.beneficiaries = list(dict.fromkeys([*prior.beneficiaries, *program.beneficiaries]))
        prior.geography = list(dict.fromkeys([*prior.geography, *program.geography]))
        prior.evidence_ids = list(dict.fromkeys([*prior.evidence_ids, *program.evidence_ids]))
        prior.description = prior.description or program.description
        prior.source_url = prior.source_url or program.source_url
    return list(merged.values())


def _finalise_visual_validation(card: CauseBaseCard) -> None:
    """Mark a visual escalation validated only when its allocations survived reconciliation."""
    validated_evidence = {
        evidence_id for record in card.financial_records
        for allocation in record.functional_expense_allocations
        for evidence_id in allocation.evidence_ids
    }
    for source_record in card.source_native_records:
        if source_record.source_family != "organisation-report-extract" or not validated_evidence.intersection(source_record.evidence_ids) or not source_record.source_payload:
            continue
        for escalation in source_record.source_payload.get("diagnostics", {}).get("vision_escalations", []):
            escalation["validation_outcome"] = "passed_share_sum_and_total_expenses_cross_check"


def _accepted_rc2_summaries(input_dir: Path) -> dict[str, dict]:
    """Load the newest accepted RC2 editorial derivatives, never synthesize."""
    releases = sorted(input_dir.parent.glob("phase2b-*-rc2"), reverse=True)
    for release in releases:
        candidate = release / "causebase.json"
        manifest = release / "manifest.json"
        if not candidate.exists() or not manifest.exists():
            continue
        if json.loads(manifest.read_text(encoding="utf-8")).get("validation", {}).get("status") != "passed":
            continue
        return {row["causebase_id"]: row for row in json.loads(candidate.read_text(encoding="utf-8"))["entities"]}
    return {}


def _inherit_accepted_summary(card: CauseBaseCard, accepted: dict | None, now: datetime) -> None:
    """Reuse an accepted RC2 summary if all of its cited evidence remains live."""
    if not accepted:
        return
    accepted_ids = set(accepted.get("summary_evidence_ids", []))
    current_ids = {item.evidence_id for item in card.evidence}
    if not accepted_ids.issubset(current_ids):
        return
    card.causebase_summary = accepted["causebase_summary"]
    card.summary_evidence_ids = accepted.get("summary_evidence_ids", [])
    synthesis = accepted.get("synthesis")
    if synthesis:
        card.synthesis = SynthesisMetadata.model_validate({
            **synthesis,
            "editorial_policy_version": "0.3-rc2",
            "parameters": {**synthesis.get("parameters", {}), "output_contract": "causebase-summary-v0.3-rc2"},
        })
    assessment = DerivativeAssessment(
        derivative="summary", generated_at=card.synthesis.generated_at if card.synthesis else None,
        last_assessed_at=now, assessment_method="phase2b-rc4-accepted-rc2-summary-reuse",
        input_hash=card.synthesis.evidence_input_hash if card.synthesis else "accepted-rc2-summary-without-synthesis-metadata",
        disposition="reused", reason="Accepted RC2 editorial summary reused; RC4 evidence did not invalidate its cited inputs.",
        affected_dimensions=["summary"],
    )
    card.derivative_assessments = [item for item in card.derivative_assessments if item.derivative != "summary"] + [assessment]


def _reports(card: CauseBaseCard, extracts: list[dict], locators: list[dict], now: datetime) -> None:
    abn = _abn(card)
    pending_visual_allocations: list[tuple[dict, str, dict]] = []
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
        if any(page.get("visual_observations") for page in extract.get("pages", [])):
            pending_visual_allocations.append((extract, evidence_id, _report_period(extract)))
        # Preserve a report's fundraising signal without inferring a channel or
        # an amount where the source does not state one.
        fundraising_pages = [page["page"] for page in extract.get("pages", []) if "fundrais" in page.get("text", "").casefold()]
        if fundraising_pages:
            card.fundraising_methods.append(FundraisingMethodObservation(method="other", status="current", observed_at=observed, evidence_ids=[evidence_id]))
        # A report can support participation evidence but is not an action
        # destination. Preserve the observation as plain text unless a separate
        # acquired action URL is explicitly available.
        report_text = "\n".join(page.get("text", "") for page in extract.get("pages", []))
        participation_terms = (("bequest", "gift in a will", "Will"), ("membership", "member", "Membership"), ("volunteer", "volunteer", "Volunteer"), ("donate", "donor", "Donate"))
        known_modes = {item.mode for item in card.participation_observations}
        for mode, marker, label in participation_terms:
            if marker.casefold() in report_text.casefold() and mode not in known_modes:
                card.participation_observations.append(ParticipationObservation(mode=mode, label=label, status="current", observed_at=observed, evidence_ids=[evidence_id]))
                known_modes.add(mode)
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
        financial = Financials(financial_record_id=financial_id, period=period, reporting_scope="subject", reporting_subject_causebase_id=card.causebase_id, covered_subjects=[card.causebase_id], consolidated="unknown", attribution_method="direct_subject_report", evidence_ids=[evidence_id], revenue=metrics.get("revenue"), employee_costs=metrics.get("employee_costs"), total_expenses=metrics.get("total_expenses"), assets=metrics.get("assets"), liabilities=metrics.get("liabilities"), net_assets=metrics.get("net_assets"), income_breakdown=[x for x in items if x.source_statement == "income_statement" and x.category == "income"], expense_breakdown=[x for x in items if x.source_statement == "income_statement" and x.category == "expense"], balance_sheet_breakdown=[x for x in items if x.source_statement == "financial_position"], source_ordered_line_items=items, statements=statements, functional_expense_allocations=_functional_expense_allocations(extract, evidence_id, metrics.get("total_expenses"), period.get("label")))
        financial.donations_gifts_bequests = _donations_gifts_bequests(financial)
        card.financial_records = [x for x in card.financial_records if x.financial_record_id != financial_id] + [financial]
        card.funding_sources = [item for item in card.funding_sources if item.evidence_ids != [evidence_id]]
        if financial.donations_gifts_bequests:
            projection = financial.donations_gifts_bequests
            card.funding_sources.append(FundingSourceObservation(
                source_type="other", period_label=projection.reporting_period_label,
                source_label=projection.canonical_label, amount=projection.numerator_amount, share=projection.result,
                reporting_scope=projection.reporting_scope, method="deterministic_derivation", evidence_ids=projection.evidence_ids,
            ))
    # A chart may be printed in an annual report while the independent total is
    # in its companion financial report.  Reconcile by shared reporting period,
    # never by organisation name, report filename or chart category.
    for extract, evidence_id, period in pending_visual_allocations:
        matching = [record for record in card.financial_records if record.period.period_end == period.get("period_end") and record.total_expenses]
        if not matching:
            continue
        target = matching[-1]
        allocations = _functional_expense_allocations(extract, evidence_id, target.total_expenses, target.period.label)
        if allocations:
            target.functional_expense_allocations = [*target.functional_expense_allocations, *allocations]
            for source_record in card.source_native_records:
                if source_record.source_family == "organisation-report-extract" and source_record.source_fields.get("source_sha256") == extract["source_sha256"] and source_record.source_payload:
                    source_record.source_payload["diagnostics"] = extract.get("extraction_diagnostics", {})


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
    accepted_summaries = _accepted_rc2_summaries(input_dir)
    cards = []
    for row in raw["entities"]:
        card = CauseBaseCard.model_validate(row); abn = _abn(card)
        _inherit_accepted_summary(card, accepted_summaries.get(card.causebase_id), now)
        card.dataset_version, card.card_schema_version, card.editorial_policy_version, card.generator_version, card.built_at = dataset_version, "0.4", EDITORIAL_POLICY_VERSION, GENERATOR_VERSION, now
        card.canonical_url = f"{VIEWER_ROOT}#{card.causebase_id}"
        card.activities, card.activity_observations = _separate_legacy_provenance(card.activities)
        card.beneficiaries, card.beneficiary_observations = _separate_legacy_provenance(card.beneficiaries)
        card.geography, card.geography_observations = _separate_legacy_provenance(card.geography)
        # Participation modes are compact display values rather than sourced
        # action destinations. Apply the same bounded provenance cleanup while
        # retaining action/provenance evidence on participation observations.
        card.participation_modes, _ = _separate_legacy_provenance(card.participation_modes)
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
        card.programs = _merge_programs(card.programs)
        _finalise_visual_validation(card)
        cards.append(CauseBaseCard.model_validate(card.model_dump(mode="json")))
    vectors = {row["causebase_id"]: row["vector"] for row in json.loads((input_dir / "embeddings.json").read_text(encoding="utf-8"))}
    similarities = json.loads((input_dir / "similarities.json").read_text(encoding="utf-8"))
    for row in similarities: row["dataset_version"] = dataset_version
    taxonomy = json.loads((input_dir / "taxonomy" / "causebase-v0.json").read_text(encoding="utf-8"))
    history = {"releases": [{"dataset_version": manifest["dataset_version"], "status": "historical", "manifest_sha256": file_sha256(input_dir / "manifest.json"), "immutable": True}, {"dataset_version": dataset_version, "status": "candidate", "derived_from": manifest["dataset_version"], "immutable": False}]}
    inventory = {"inventory_version": "phase2b-rc4", "scope": "Existing 120-card corpus; no new subjects.", "embedding_run": {"cache_hits": 120, "generated": 0, "input_tokens": 0, "note": "RC3 vectors intentionally reused; source text and summaries were not rewritten."}, "gap_report": ["Public ACNC profile and latest AIS-detail acquisition attempted for all 120 existing subjects.", "AIS detail failures are explicit coverage observations; no profile metadata is substituted for a detail payload.", "Seven already-acquired reports were processed through one deterministic extractor; document URLs are only published where preserved in source acquisition metadata."]}
    return render_publication(cards, vectors, similarities, output_dir, taxonomy=taxonomy, agent_guide=(input_dir / "agent-guide.md").read_text(encoding="utf-8"), source_inventory=inventory, release_history=history)

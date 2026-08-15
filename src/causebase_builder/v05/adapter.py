"""Deterministic RC4-to-0.5 fixture adapter; no I/O, fetching, or model calls."""
from __future__ import annotations
from copy import deepcopy
from .models import ReleaseContext, CapabilityRegistry

class MigrationBlocker(ValueError):
    """Raised when immutable RC4 data cannot be represented without guessing."""

def _sign(money: dict | None) -> str:
    if money is None: return "not_applicable"
    value = money["source_amount"]
    return "negative" if value.startswith("-") else "zero" if value == "0" else "positive"

def _row(row: dict, causebase_id: str, source_record_id: str, period: dict) -> dict:
    return {"observation_id": row["observation_id"], "subject_id": causebase_id, "kind": "financial_statement_row", "claim_basis": "direct", "extraction_method": "table", "source_record_ids": [source_record_id], "evidence_ids": row["evidence_ids"], "time": {"reporting_period": period}, "confidence": row.get("extraction_confidence"), "warnings": row.get("extraction_warnings", []), "source_label": row["source_label"], "row_type": row["row_type"], "source_order": row["source_order"], "hierarchy_indent": row.get("hierarchy_indent"), "amount": row.get("current_amount"), "comparatives": [{"period": {"label": item.get("label")}, "amount": item["amount"]} for item in row.get("comparative_periods", [])], "source_location": row.get("source_location"), "source_sign": _sign(row.get("current_amount"))}

def adapt_rc4_fixture(rc4: dict, template: dict, context: ReleaseContext) -> dict:
    """Map governed RC4 statement structure into a supplied 0.5 card shape.

    The template supplies only approved target release/domain choices; source rows
    are always reconstructed from the RC4 input and no subject-specific branch is used.
    """
    card = deepcopy(template)
    card.pop("source_statement_fixture", None)
    card["release"] = context.model_dump(exclude={"capability_registry"})
    record = next((x for x in rc4.get("financial_records", []) if x.get("statements")), None)
    if record:
        source_id = card["financial_reports"][0]["source_record_id"]
        period = {"label": card["financial_reports"][0]["reporting_period"].get("label")}
        prior={x["statement_type"]: x for x in card["financial_reports"][0].get("statements", [])}; statements=[]
        for source in record["statements"]:
            if source["statement_type"] not in {"profit_and_loss", "financial_position"}: continue
            statements.append({"statement_id": prior.get(source["statement_type"], {}).get("statement_id", f"stmt:{card['causebase_id']}:{source['statement_type']}"), "statement_type": source["statement_type"], "printed_title": source["statement_title"], "reporting_period": period, "reporting_scope": source.get("reporting_scope", "unknown"), "currency": source.get("currency"), "source_location": None, "rows": [_row(row, card["causebase_id"], source_id, period) for row in source["rows"]]})
        card["financial_reports"][0]["statements"] = statements
    return card

def adapt_rc4_card(rc4_card: dict, source_records: dict[str, dict], capability_registry: CapabilityRegistry, release_context: ReleaseContext) -> dict:
    """Adapt one RC4 public card without a target template or fixture input.

    This deliberately fails closed for legacy display observations that have no
    evidence binding: inventing provenance or silently deleting them would both
    violate the approved v0.5 migration rules.
    """
    for field in ("activity_observations", "beneficiary_observations", "geography_observations"):
        if any(not value.get("evidence_ids") for value in rc4_card.get(field, [])):
            raise MigrationBlocker(f"{rc4_card['causebase_id']}: {field} contains provenance-free legacy observations")
    evidence=[{"evidence_id": x["evidence_id"], "title": x["title"], **({"url":x["url"]} if x.get("url") else {})} for x in rc4_card.get("evidence", [])]
    source_refs=[x["source_record_id"] for x in rc4_card.get("source_native_records", []) if x["source_record_id"] in source_records]
    identity={"legal_name":rc4_card["legal_name"],"display_name":rc4_card["display_name"],"operating_names":rc4_card.get("operating_names",[]),"former_names":rc4_card.get("former_names",[]),"entity_status":rc4_card.get("entity_status"),"website":rc4_card.get("website"),"external_identifiers":[{"scheme":x["scheme"],"value":x["value"],"evidence_ids":[x["source_evidence_id"]] if x.get("source_evidence_id") else []} for x in rc4_card.get("external_identifiers",[])],"registrations":[{"regulator":x["regulator"],"status":x.get("status"),"evidence_ids":x.get("evidence_ids",[])} for x in rc4_card.get("registrations",[])],"tax_statuses":[{"scheme":x["scheme"],"status":x.get("status"),"evidence_ids":x.get("evidence_ids",[])} for x in rc4_card.get("tax_statuses",[])]}
    legacy_coverage={x["capability"]:x for x in rc4_card.get("coverage",[])}
    aliases={"regulatory.acnc_profile":"regulatory","regulatory.ais":"latest_acnc_ais","web.website":"website","report.annual_report":"annual_report","financial.report":"financials","financial.statements":"financials","fundraising.expenditure":"fundraising_expenditure"}
    coverage=[]
    for cap in capability_registry.capabilities:
        legacy=legacy_coverage.get(aliases.get(cap.capability_id,"")); coverage.append({"capability":cap.capability_id,"status":legacy["status"] if legacy else "not_yet_processed","assessed_at":(legacy.get("observed_at") if legacy else release_context.generated_at),"source_record_ids":[legacy["source_record_id"]] if legacy and legacy.get("source_record_id") else [],"evidence_ids":legacy.get("evidence_ids",[]) if legacy else []})
    return {"causebase_id":rc4_card["causebase_id"],"contract_version":"0.5","subject_kind":rc4_card["subject_kind"],"identity":identity,"release":release_context.model_dump(exclude={"capability_registry"}),"source_record_refs":source_refs,"source_bindings":[{"source_record_id":x["source_record_id"],"resolution_status":x["resolution_status"],"resolution_basis":x.get("resolution_basis"),"confidence":x["confidence"],"review_status":x["review_status"],"conflicting_signals":x.get("conflicting_signals",[])} for x in rc4_card.get("source_resolutions",[])],"evidence":evidence,"summary":None,"activities":[],"beneficiaries":[],"descriptive_geography":[],"navigation_geography":rc4_card.get("navigation_geography",[]),"funding_sources":[],"fundraising_methods":[],"participation":[],"opportunities":[],"programs":[],"relationships":[],"classifications":[],"coverage":{"registry_id":capability_registry.registry_id,"current":coverage},"financial_reports":[],"canonical_metrics":[],"analytic_projections":[],"derivatives":[]}

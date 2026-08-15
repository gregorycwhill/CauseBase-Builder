"""Deterministic RC4-to-0.5 fixture adapter; no I/O, fetching, or model calls."""
from __future__ import annotations
from copy import deepcopy
from .models import ReleaseContext

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

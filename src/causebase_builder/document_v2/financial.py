"""Source-faithful statement reconstruction and output-only Golden comparison."""
from __future__ import annotations

import json
from pathlib import Path

from ..phase2d import _report_rows, _statements


def reconstruct_statements(result: dict) -> dict:
    pages=[{"page": page["page"], "text": page.get("text", "")} for page in result.get("pages", [])]
    rows=_report_rows({"pages": pages})
    statements=_statements(rows, "ev:document-v2", {"label": "document extraction evaluation"})
    return {statement.statement_type: statement.model_dump(mode="json") for statement in statements}


def score_eja_statements(reconstructed: dict, gold_card: Path) -> dict:
    """Compare only after extraction/reconstruction; gold never configures a candidate."""
    gold=json.loads(gold_card.read_text(encoding="utf8"))
    expected={statement["statement_type"]: statement for statement in gold["financial_reports"][0]["statements"]}
    outcomes={}
    for kind in ("profit_and_loss", "financial_position"):
        actual=reconstructed.get(kind, {"rows": []})["rows"]; target=expected[kind]["rows"]
        labels=[row["source_label"] for row in actual]; target_labels=[row["source_label"] for row in target]
        issues=[]
        for index, (candidate, truth) in enumerate(zip(actual, target)):
            if candidate["source_label"] != truth["source_label"]: issues.append({"kind": "label_or_order", "row": index, "actual": candidate["source_label"], "expected": truth["source_label"]})
            candidate_amount=(candidate.get("current_amount") or {}).get("normalised_amount")
            truth_amount=(truth.get("amount") or {}).get("normalised_amount")
            if candidate_amount != truth_amount: issues.append({"kind": "current_value", "row": index})
            candidate_sign="negative" if str(candidate_amount or "").startswith("-") else "positive" if candidate_amount is not None else None
            if truth.get("source_sign") in {"positive", "negative"} and candidate_sign != truth.get("source_sign"):
                issues.append({"kind": "sign", "row": index})
            candidate_comps=[item.get("amount", {}).get("normalised_amount") for item in candidate.get("comparative_periods", [])]
            truth_comps=[item.get("amount", {}).get("normalised_amount") for item in truth.get("comparatives", [])]
            if candidate_comps != truth_comps: issues.append({"kind": "comparative", "row": index})
            if candidate.get("row_type") != truth.get("row_type") or candidate.get("hierarchy_indent") != truth.get("hierarchy_indent"): issues.append({"kind": "hierarchy_or_row_type", "row": index})
        outcomes[kind]={"expected_rows": len(target), "actual_rows": len(actual), "missing_rows": [label for label in target_labels if label not in labels], "extra_rows": [label for label in labels if label not in target_labels], "issues": issues, "passed": len(actual) == len(target) and not issues}
    return outcomes

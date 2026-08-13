"""Emit a private, deterministic RC4 acceptance-audit summary."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    cards = json.loads((args.candidate / "causebase.json").read_text(encoding="utf-8"))["entities"]
    report_cards = [card for card in cards if any(record["source_family"] == "organisation-report-extract" for record in card["source_native_records"])]
    ais = [record for card in cards for record in card["source_native_records"] if record["source_family"] == "acnc-ais-detail"]
    latest_ais_coverage = [next((item for item in card["coverage"] if item["capability"] == "latest_acnc_ais"), None) for card in cards]
    audit = {
        "card_count": len(cards),
        "ais_detail": {"attempted": len(ais), "payload_acquired": sum(bool(record.get("source_payload")) for record in ais), "explicit_failure": sum(not bool(record.get("source_payload")) for record in ais), "no_submitted_ais": sum(item is not None and item["status"] == "not_available_from_source" for item in latest_ais_coverage), "coverage_observations": len([item for item in latest_ais_coverage if item])},
        "reports": {"source_native_extract_records": sum(1 for card in cards for record in card["source_native_records"] if record["source_family"] == "organisation-report-extract"), "cards": [{"causebase_id": card["causebase_id"], "abn": next((item["value"] for item in card["external_identifiers"] if item["scheme"].lower() == "abn"), None), "reports": [record["source_fields"]["filename"] for record in card["source_native_records"] if record["source_family"] == "organisation-report-extract"]} for card in report_cards]},
        "coverage_conflicts": [card["causebase_id"] for card in cards if any(record["source_family"] == "organisation-report-extract" for record in card["source_native_records"]) and any(item["capability"] in {"annual_report", "financials"} and item["status"] == "not_yet_processed" for item in card["coverage"])],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

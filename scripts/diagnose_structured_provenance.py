"""Write a private, reviewable list of residual source narration in display values."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

PATTERN = re.compile(r"as described|website|as advertised|site states|organisation says", re.I)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    cards = json.loads((args.candidate / "causebase.json").read_text(encoding="utf-8"))["entities"]
    findings = [
        {"causebase_id": card["causebase_id"], "field": field, "value": value}
        for card in cards
        for field in ("activities", "beneficiaries", "geography", "participation_modes")
        for value in card.get(field, [])
        if PATTERN.search(value)
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"status": "requires_evidence_aware_human_review", "findings": findings}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

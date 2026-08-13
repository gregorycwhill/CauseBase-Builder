"""Create a bounded private locator inventory from acquired public ACNC profiles.

This performs no organisation-specific selection.  It records the current
website and every regulator-hosted annual/financial report locator already
present in the profile payload, with the ACNC profile as the discovery source.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    entities = json.loads(args.profiles.read_text(encoding="utf-8"))["entities"]
    discovery = {}
    for abn, wrapped in entities.items():
        data = wrapped["profile"]["data"]
        reports = []
        for document in data.get("Documents") or []:
            kind = str(document.get("type") or "")
            url = document.get("Url")
            if url and kind in {"Annual Report", "Financial Report"}:
                reports.append({"title": document.get("Title") or url, "url": url, "type": kind, "year": str(document.get("Year") or "") or None, "published_at": document.get("Date")})
        discovery[abn] = {"website": data.get("Website"), "reports": reports, "discovery_basis": "ACNC public profile Documents and Website fields"}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"source": "ACNC public profile acquisition", "entities": discovery}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

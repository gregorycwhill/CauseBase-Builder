"""Acquire the public ACNC profile payload for an existing CauseBase release.

The saved payload is a source artifact, not a derived claim.  It deliberately
contains only the ABNs already present in the input publication.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE = "https://www.acnc.gov.au/api/dynamics"


def fetch_json(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "CauseBase source refresh/0.4"})
    with urlopen(request, timeout=45) as response:  # nosec B310: fixed public HTTPS host
        return json.loads(response.read().decode("utf-8"))


def acquire(abn: str) -> dict:
    search = fetch_json(f"{BASE}/search/charity?{urlencode({'search': abn})}")
    matches = [row for row in search.get("results", []) if row.get("data", {}).get("Abn") == abn]
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one public ACNC result for {abn}, found {len(matches)}")
    uuid = matches[0]["uuid"]
    entity = fetch_json(f"{BASE}/entity/{uuid}")
    if entity.get("data", {}).get("Abn") != abn:
        raise RuntimeError(f"ACNC entity ABN mismatch for {abn}")
    return entity


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    rows = json.loads(args.input.read_text(encoding="utf-8"))["entities"]
    abns = sorted({item["value"] for row in rows for item in row.get("external_identifiers", []) if item.get("scheme", "").lower() == "abn"})
    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(acquire, abn): abn for abn in abns}
        for future in as_completed(futures):
            abn = futures[future]
            results[abn] = future.result()
            print(f"acquired {len(results)}/{len(abns)}: {abn}", file=sys.stderr)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"source": "ACNC public charity API", "entities": results}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

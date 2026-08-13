"""Deterministically extract the already-acquired private report artifacts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from causebase_builder.sources.documents import extract_pdf_evidence
from causebase_builder.sources.vision import openai_narrow_vision_extractor


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reports-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--vision-model", help="Optional OpenAI model; only unresolved pages are sent, individually.")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    documents = []
    for pdf in sorted(args.reports_root.rglob("*.pdf")):
        extracted = extract_pdf_evidence(pdf, vision_extractor=openai_narrow_vision_extractor(args.vision_model) if args.vision_model else None)
        abn = next((part for part in pdf.parts if part.isdigit() and len(part) == 11), "unknown")
        target = args.out / f"{abn}-{pdf.stem.replace(' ', '-')}.json"
        target.write_text(json.dumps({"abn": abn, "filename": pdf.name, **extracted}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        documents.append({"abn": abn, "filename": pdf.name, "extract": target.name, "sha256": extracted["source_sha256"], "pages": extracted["extracted_page_count"]})
    (args.out / "manifest.json").write_text(json.dumps({"documents": documents}, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

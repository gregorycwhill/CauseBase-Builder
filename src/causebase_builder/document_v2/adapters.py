"""Private adapters for independently useful PDF-extraction components.

The adapters preserve their natural strengths: a table specialist is not
pretended to be a prose/OCR stack.  All outputs use the minimum common syntax
contract needed by the Golden Corpus evaluator.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def _version(package: str) -> str:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return "unavailable"


def available_candidates() -> dict[str, dict]:
    return {
        "pdfplumber": {"kind": "primary", "version": _version("pdfplumber")},
        "pymupdf": {"kind": "primary", "version": _version("pymupdf")},
        "camelot-stream": {"kind": "table_specialist", "version": _version("camelot-py")},
        "camelot-lattice": {"kind": "table_specialist", "version": _version("camelot-py")},
        "tesseract": {"kind": "ocr_specialist", "version": _tesseract_version()},
        "rapidocr": {"kind": "ocr_specialist", "version": _version("rapidocr-onnxruntime")},
    }


def _tesseract_version() -> str:
    executable = shutil.which("tesseract") or str(Path("C:/Program Files/Tesseract-OCR/tesseract.exe"))
    if not Path(executable).exists() and not shutil.which("tesseract"):
        return "unavailable"
    result = subprocess.run([executable, "--version"], capture_output=True, text=True, check=False)
    return result.stdout.splitlines()[0].replace("tesseract ", "") if result.returncode == 0 else "unavailable"


def _cache_path(document: Path, candidate: str, version: str, cache_root: Path | None) -> Path | None:
    if cache_root is None:
        return None
    digest = hashlib.sha256(document.read_bytes()).hexdigest()
    safe = hashlib.sha256(f"{candidate}:{version}:document-v2.2".encode()).hexdigest()[:12]
    return cache_root / "document-v2" / f"{digest}-{safe}.json"


def _pdfplumber(document: Path, *, tables: bool = True) -> list[dict]:
    import pdfplumber
    pages=[]
    with pdfplumber.open(document) as pdf:
        for number, page in enumerate(pdf.pages, 1):
            text=page.extract_text(layout=False) or ""
            blocks=[{"text": word["text"], "x0": word["x0"], "top": word["top"], "x1": word["x1"], "bottom": word["bottom"]} for word in page.extract_words(use_text_flow=True)]
            found=[]
            if tables:
                for index, table in enumerate(page.find_tables(), 1):
                    found.append({"table_index": index, "location": {"page": number, "bbox": list(table.bbox)}, "rows": [[cell or "" for cell in row] for row in table.extract()], "engine": "pdfplumber"})
            pages.append({"page": number, "text": text, "blocks": blocks, "tables": found, "figures": [], "route": "native" if len(text.strip()) >= 40 else "low_text"})
    return pages


def _pymupdf(document: Path) -> list[dict]:
    import pymupdf
    pages=[]
    with pymupdf.open(document) as pdf:
        for number, page in enumerate(pdf, 1):
            blocks=[{"text": item[4].strip(), "x0": item[0], "top": item[1], "x1": item[2], "bottom": item[3]} for item in page.get_text("blocks", sort=True) if item[4].strip()]
            tables=[]
            try:
                for index, table in enumerate(page.find_tables().tables, 1):
                    tables.append({"table_index": index, "location": {"page": number, "bbox": list(table.bbox)}, "rows": [[cell or "" for cell in row] for row in table.extract()], "engine": "pymupdf"})
            except Exception as exc:
                tables.append({"table_index": 0, "location": {"page": number}, "rows": [], "engine": "pymupdf", "warning": f"table_detection:{type(exc).__name__}"})
            text=page.get_text("text", sort=True)
            pages.append({"page": number, "text": text, "blocks": blocks, "tables": tables, "figures": [{"location": {"page": number, "bbox": list(image[:4])}} for image in page.get_images(full=True)], "route": "native" if len(text.strip()) >= 40 else "low_text"})
    return pages


def _camelot(document: Path, flavor: str) -> list[dict]:
    # Camelot is deliberately table-only; attach PyMuPDF text for the common
    # page contract without claiming that Camelot recovered that prose.
    import camelot
    pages=_pymupdf(document)
    # Generic statement-page routing, not a document-specific tune: table
    # specialists are evaluated only where a native pass sees a financial
    # statement heading. This avoids spending minutes rasterising narrative
    # pages where Camelot itself cannot usefully operate.
    markers=("statement of profit", "statement of financial position", "income statement", "balance sheet", "statement of cash flows")
    selected=[str(page["page"]) for page in pages if any(marker in page["text"].casefold() for marker in markers)]
    if not selected:
        return pages
    tables=camelot.read_pdf(str(document), pages=",".join(selected), flavor=flavor)
    for index, table in enumerate(tables, 1):
        page=pages[int(table.page)-1]
        page["tables"].append({"table_index": index, "location": {"page": int(table.page), "bbox": list(getattr(table, "bbox", ()) or ())}, "rows": table.df.fillna("").values.tolist(), "engine": f"camelot-{flavor}", "metadata": table.parsing_report})
    return pages


def _ocr_pages(document: Path, engine: str) -> list[dict]:
    # OCR is only applied to genuinely low-native-text pages.  Native text and
    # coordinates remain the primary evidence for digital pages.
    import numpy as np
    import pdfplumber
    pages=_pdfplumber(document, tables=False)
    with pdfplumber.open(document) as pdf:
        for target, source in zip(pages, pdf.pages):
            if target["route"] != "low_text":
                continue
            image=source.to_image(resolution=144).original.convert("RGB")
            if engine == "tesseract":
                executable=shutil.which("tesseract") or "C:/Program Files/Tesseract-OCR/tesseract.exe"
                with tempfile.TemporaryDirectory(prefix="causebase-v2-ocr-") as directory:
                    input_path=Path(directory)/"page.png"; output=Path(directory)/"output"; image.save(input_path)
                    completed=subprocess.run([executable, str(input_path), str(output), "--psm", "6"], capture_output=True, text=True, timeout=60, check=False)
                    text=output.with_suffix(".txt").read_text(encoding="utf8", errors="replace") if completed.returncode == 0 and output.with_suffix(".txt").exists() else ""
                blocks=[]
            else:
                from rapidocr_onnxruntime import RapidOCR
                result, _ = RapidOCR()(np.array(image))
                text="\n".join(item[1] for item in (result or [])); blocks=[{"text": item[1], "x0": item[0][0][0], "top": item[0][0][1], "x1": item[0][2][0], "bottom": item[0][2][1]} for item in (result or [])]
            target.update({"text": text, "blocks": blocks, "route": engine, "ocr": {"used": True, "engine": engine, "version": available_candidates()[engine]["version"]}})
    return pages


def extract_candidate(document: Path, candidate: str, *, cache_root: Path | None = None) -> dict:
    inventory=available_candidates(); meta=inventory.get(candidate)
    if meta is None or meta["version"] == "unavailable":
        return {"result_contract": "causebase.document_extraction.v2", "candidate": candidate, "status": "unavailable", "failures": ["candidate_unavailable"]}
    cache=_cache_path(document, candidate, meta["version"], cache_root)
    if cache and cache.exists(): return {**json.loads(cache.read_text(encoding="utf8")), "cache_status": "hit"}
    if candidate == "pdfplumber": pages=_pdfplumber(document)
    elif candidate == "pymupdf": pages=_pymupdf(document)
    elif candidate.startswith("camelot-"): pages=_camelot(document, candidate.removeprefix("camelot-"))
    elif candidate in {"tesseract", "rapidocr"}: pages=_ocr_pages(document, candidate)
    else: raise ValueError(f"unknown document candidate {candidate}")
    result={"result_contract": "causebase.document_extraction.v2", "candidate": candidate, "candidate_version": meta["version"], "status": "completed", "document": {"filename": document.name, "sha256": hashlib.sha256(document.read_bytes()).hexdigest(), "page_count": len(pages)}, "pages": pages, "failures": [], "cache_status": "miss"}
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True); cache.write_text(json.dumps(result, ensure_ascii=False), encoding="utf8")
    return result

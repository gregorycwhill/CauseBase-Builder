"""Production private syntax pipeline assembled from validated routes."""
from __future__ import annotations

from pathlib import Path
import re

from .adapters import available_candidates, extract_candidate
from .visual import extract_vector_percentage_chart

PIPELINE_VERSION="document-v2.3"


def extract_document(document: Path, *, cache_root: Path | None = None, options: dict | None = None) -> dict:
    """Extract private source syntax without semantic/canonical interpretation.

    The validated normal route is pdfplumber.  OCR is page-routed only when
    native text is low and is independently cache-keyed by its engine/version.
    Vector visual extraction is page-routed locally where native drawing
    primitives are present. It neither transmits source material nor makes
    CauseBase semantic claims.
    """
    options=options or {}
    primary=options.get("primary_engine", "pdfplumber")
    ocr_engine=options.get("ocr_engine", "tesseract")
    primary_result=extract_candidate(document, primary, cache_root=cache_root)
    if primary_result["status"] != "completed": return primary_result
    pages=primary_result["pages"]
    ocr_status={"used": False, "engine": ocr_engine, "status": "not_needed"}
    if any(page["route"] == "low_text" for page in pages):
        ocr_result=extract_candidate(document, ocr_engine, cache_root=cache_root)
        if ocr_result["status"] == "completed":
            for target, recovered in zip(pages, ocr_result["pages"]):
                if target["route"] == "low_text" and recovered.get("route") == ocr_engine and recovered.get("text", "").strip():
                    target.update({"text": recovered["text"], "blocks": recovered.get("blocks", []), "route": ocr_engine, "ocr": recovered.get("ocr")})
                    ocr_status={"used": True, "engine": ocr_engine, "status": "used"}
        else: ocr_status={"used": False, "engine": ocr_engine, "status": "unavailable"}
    visual_pages=[]
    if options.get("enable_vector_visual", True):
        for page in pages:
            # A percentage token is a generic, cheap precondition for this
            # percentage-chart adapter; avoid opening every graphical page.
            if page.get("vector_graphics", 0) < 4 or not re.search(r"\b\d{1,3}%", page.get("text", "")): continue
            visual=extract_vector_percentage_chart(document, page["page"], cache_root=cache_root)
            if visual["observations"]:
                page["visual"]=visual; visual_pages.append(page["page"])
    return {**primary_result, "pipeline_version": PIPELINE_VERSION, "options": {"primary_engine": primary, "ocr_engine": ocr_engine, **options}, "pages": pages, "lineage": {"primary": {"name": primary, "version": available_candidates()[primary]["version"]}, "ocr": {"name": ocr_engine, "version": available_candidates().get(ocr_engine, {}).get("version")}, "visual": {"name":"local_vector_colour_geometry", "implementation_version":"1", "pages":visual_pages}}, "ocr": ocr_status}

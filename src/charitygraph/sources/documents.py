"""Private, reproducible extraction of report evidence for the reality spike."""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import subprocess
import tempfile
from decimal import Decimal
from pathlib import Path
from datetime import datetime, timezone
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pdfplumber

from ..models import MoneyObservation


VisionExtractor = Callable[[dict], list[dict]]


def _page_is_visually_nonempty(page) -> tuple[bool, float]:
    """Render one page only and measure non-white coverage without retaining it."""
    image = page.to_image(resolution=144).original.convert("L")
    pixels = image.histogram()
    non_white = sum(pixels[:245])
    coverage = non_white / max(image.width * image.height, 1)
    # A sparse table can still be substantive on an otherwise white scanned
    # page; classification is deliberately sensitive, while later salience
    # checks and OCR decide whether to escalate further.
    return coverage >= 0.00001, coverage


def _local_ocr(image) -> tuple[str, str | None]:
    """Use locally installed Tesseract when present; no remote OCR fallback."""
    executable = shutil.which("tesseract")
    if not executable:
        return "", "local_ocr_unavailable"
    with tempfile.TemporaryDirectory(prefix="causebase-ocr-") as directory:
        source = Path(directory) / "page.png"
        target = Path(directory) / "ocr"
        image.save(source, format="PNG")
        result = subprocess.run(
            [executable, str(source), str(target), "--psm", "6"],
            capture_output=True, text=True, timeout=60, check=False,
        )
        text_path = target.with_suffix(".txt")
        if result.returncode or not text_path.exists():
            return "", "local_ocr_failed"
        return text_path.read_text(encoding="utf-8", errors="replace"), None


def _visual_relationships_unresolved(text: str, *, visually_nonempty: bool, graphic_structure: bool) -> bool:
    """Conservative chart/table trigger; it never attempts arbitrary chart reading."""
    percentages = re.findall(r"(?<!\d)\d{1,3}(?:\.\d+)?%", text)
    labels = [line for line in text.splitlines() if re.search(r"[A-Za-z]", line)]
    return visually_nonempty and graphic_structure and len(percentages) >= 2 and len(labels) >= 3


def fetch_pdf_document(url: str, *, timeout_seconds: int = 30, max_bytes: int = 20_000_000) -> dict:
    """Fetch one public PDF with bounded size and coverage-safe failure metadata.

    The caller owns archival of the returned bytes.  This function deliberately
    does not treat a linked HTML page or an over-sized file as report evidence.
    """
    retrieved_at = datetime.now(timezone.utc).isoformat()
    request = Request(url, headers={"User-Agent": "CauseBase-Phase2A/0.1 (+public-report-evidence)"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                return {"source_url": url, "retrieved_at": retrieved_at, "status": "retrieval_failed", "error_class": "response_too_large"}
            content_type = response.headers.get_content_type()
            if content_type != "application/pdf" and not body.startswith(b"%PDF-"):
                return {"source_url": response.geturl(), "retrieved_at": retrieved_at, "status": "retrieval_failed", "error_class": f"unsupported_content_type:{content_type}"}
            return {
                "source_url": response.geturl(), "requested_url": url, "retrieved_at": retrieved_at,
                "status": "observed", "content_sha256": hashlib.sha256(body).hexdigest(), "pdf_bytes": body,
            }
    except HTTPError as error:
        return {"source_url": url, "retrieved_at": retrieved_at, "status": "retrieval_failed", "error_class": f"http_{error.code}"}
    except (URLError, TimeoutError):
        return {"source_url": url, "retrieved_at": retrieved_at, "status": "retrieval_failed", "error_class": "connection_failed"}


def parse_money_observation(
    raw_value: str, *, currency: str = "AUD", unit_scale: Decimal | int = 1, unit_label: str | None = None
) -> MoneyObservation:
    """Parse a printed statement value without losing its presentation scale."""
    cleaned = raw_value.strip().replace(",", "")
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    if negative:
        cleaned = cleaned[1:-1].strip()
    value = Decimal(cleaned)
    if negative:
        value = -value
    scale = Decimal(str(unit_scale))
    return MoneyObservation(
        source_amount=value,
        source_currency=currency,
        source_unit_scale=scale,
        normalised_amount=value * scale,
        normalised_currency=currency,
        source_unit_label=unit_label,
        source_raw_value=raw_value,
    )


def extract_pdf_evidence(
    path: Path, max_pages: int | None = None, start_page: int = 1,
    vision_extractor: VisionExtractor | None = None,
) -> dict:
    """Return page-level evidence with bounded OCR and visual escalation.

    The optional visual extractor receives one rendered page/crop payload at a
    time.  It is intentionally an injected adapter: this module never sends a
    whole report, and installations without an approved local adapter retain a
    clear `not_configured` outcome rather than inventing observations.
    """
    if start_page < 1:
        raise ValueError("start_page must be positive")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    pages = []
    with pdfplumber.open(path) as document:
        source_page_count = len(document.pages)
        for number, page in enumerate(document.pages, start=1):
            if number < start_page:
                continue
            if max_pages is not None and number >= start_page + max_pages:
                break
            tables = [
                [[cell or "" for cell in row] for row in table]
                for table in page.extract_tables()
            ]
            text = page.extract_text() or ""
            # Rendering is local and page-scoped.  It detects vector charts as
            # well as embedded raster scans; it does not imply a vision call.
            image = page.to_image(resolution=144).original
            visually_nonempty, raster_coverage = _page_is_visually_nonempty(page)
            graphic_structure = len(page.images) > 0 or len(page.curves) >= 3 or len(page.rects) >= 10
            page_state = "native_text_sufficient"
            page_states = [page_state]
            ocr_text, ocr_warning = "", None
            if len(text.strip()) < 40 and visually_nonempty:
                page_state = "image_only_or_scanned"
                page_states = [page_state]
                ocr_text, ocr_warning = _local_ocr(image)
            salience_text = text if len(text.strip()) >= 40 else ocr_text
            if _visual_relationships_unresolved(salience_text, visually_nonempty=visually_nonempty, graphic_structure=graphic_structure):
                page_state = "visual_relationships_unresolved"
                page_states.append(page_state)
            visual = []
            escalation = None
            if page_state == "visual_relationships_unresolved":
                escalation = {
                    "document": path.name, "page": number, "crop": "full_page",
                    "trigger_reason": "labels_and_percentages_present_but_spatial_relationships_unresolved",
                    "model": None, "usage": None, "cost": None, "validation_outcome": "not_configured",
                }
                if vision_extractor:
                    buffer = io.BytesIO(); (image or page.to_image(resolution=144).original).save(buffer, format="PNG")
                    response = vision_extractor({"document": path.name, "page": number, "crop": "full_page", "image_png": buffer.getvalue(), "native_text": text, "ocr_text": ocr_text})
                    raw_visual = response if isinstance(response, list) else response.get("observations", [])
                    visual = [
                        {**item, "page": item.get("page", number), "extraction_method": item.get("extraction_method", "narrow_vision_structured")}
                        for item in raw_visual
                    ]
                    metadata = {} if isinstance(response, list) else response
                    escalation.update({"model": metadata.get("model", "configured_narrow_vision"), "usage": metadata.get("usage"), "cost": metadata.get("cost"), "validation_outcome": "pending_cross_check"})
            pages.append(
                {
                    "page": number,
                    "text": text,
                    "tables": tables,
                    "native_text_characters": len(text.strip()),
                    "table_count": len(tables),
                    "extraction_method": "native_text_and_tables",
                    # OCR is page-scoped and only considered when this flag is
                    # true; no whole-document image conversion is permitted.
                    "needs_ocr_review": len(text.strip()) < 40,
                    "page_state": page_state,
                    "page_states": page_states,
                    "visually_nonempty": visually_nonempty,
                    "raster_coverage": round(raster_coverage, 6),
                    "graphic_structure": graphic_structure,
                    "ocr_text": ocr_text,
                    "ocr_warning": ocr_warning,
                    "visual_observations": visual,
                    "vision_escalation": escalation,
                }
            )
    return {
        "source_sha256": digest,
        "page_count": source_page_count,
        "extracted_page_count": len(pages),
        "truncated": max_pages is not None and source_page_count >= start_page + max_pages,
        "extraction_diagnostics": {
            "native_text_pages": sum(1 for page in pages if page["native_text_characters"] >= 40),
            "low_text_pages": [page["page"] for page in pages if page["needs_ocr_review"]],
            "ocr_attempted_pages": [],
            "image_only_or_scanned_pages": [page["page"] for page in pages if page["page_state"] == "image_only_or_scanned"],
            "visual_relationships_unresolved_pages": [page["page"] for page in pages if page["page_state"] == "visual_relationships_unresolved"],
            "vision_escalations": [page["vision_escalation"] for page in pages if page["vision_escalation"]],
        },
        "pages": pages,
    }

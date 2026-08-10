"""Private, reproducible extraction of report evidence for the reality spike."""

from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pdfplumber

from ..models import MoneyObservation


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
    path: Path, max_pages: int | None = None, start_page: int = 1
) -> dict:
    """Return page-level text/tables; bounds support targeted evidence review."""
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
            pages.append(
                {
                    "page": number,
                    "text": page.extract_text() or "",
                    "tables": tables,
                }
            )
    return {
        "source_sha256": digest,
        "page_count": source_page_count,
        "extracted_page_count": len(pages),
        "truncated": max_pages is not None and source_page_count >= start_page + max_pages,
        "pages": pages,
    }

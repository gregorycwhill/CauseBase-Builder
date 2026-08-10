"""Small deterministic web-snapshot text extractor for evidence review."""

from __future__ import annotations

from html.parser import HTMLParser
import hashlib
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urljoin


class _ReadableText(HTMLParser):
    _ignored = {"script", "style", "nav", "footer", "header", "noscript"}
    _control_labels = {"search", "donate", "open menu", "close menu", "skip to content"}

    def __init__(self) -> None:
        super().__init__()
        self._ignored_depth = 0
        self._content_depth = 0
        self.parts: list[str] = []
        self.content_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self._ignored:
            self._ignored_depth += 1
        if tag in {"main", "article"}:
            self._content_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._ignored and self._ignored_depth:
            self._ignored_depth -= 1
        if tag in {"main", "article"} and self._content_depth:
            self._content_depth -= 1

    def handle_data(self, data: str) -> None:
        cleaned = data.strip()
        if not self._ignored_depth and cleaned and cleaned.casefold() not in self._control_labels:
            self.parts.append(cleaned)
            if self._content_depth:
                self.content_parts.append(cleaned)


def extract_web_snapshot(html: str) -> str:
    parser = _ReadableText()
    parser.feed(html)
    return " ".join(parser.content_parts or parser.parts)


class _ReportLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._href: str | None = None
        self._text: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href:
            self.links.append((self._href, " ".join(self._text).strip()))
            self._href, self._text = None, []


def discover_report_links(html: str, base_url: str) -> list[str]:
    parser = _ReportLinks()
    parser.feed(html)
    found = []
    canonical_base = base_url if base_url.startswith(("http://", "https://")) else f"https://{base_url}"
    for href, label in parser.links:
        candidate = urljoin(canonical_base, href)
        marker = f"{href} {label}".casefold()
        if any(word in marker for word in ("annual report", "financial report", "annual-report", "annual_report")):
            found.append(candidate)
    return sorted(set(found))[:3]


def fetch_web_evidence(url: str, *, timeout_seconds: int = 20, max_bytes: int = 1_000_000) -> dict:
    """Fetch one public page and return bounded extractable evidence metadata.

    Callers own durable archival; failure returns coverage-safe metadata instead
    of raising so website problems never block structured-source updates.
    """
    canonical_url = url if url.startswith(("http://", "https://")) else f"https://{url}"
    request = Request(canonical_url, headers={"User-Agent": "CauseBase-Phase2A/0.1 (+public-evidence)"})
    retrieved_at = datetime.now(timezone.utc).isoformat()
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                return {"source_url": canonical_url, "retrieved_at": retrieved_at, "status": "retrieval_failed", "error_class": "response_too_large"}
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "application/xhtml+xml"}:
                return {"source_url": canonical_url, "retrieved_at": retrieved_at, "status": "retrieval_failed", "error_class": f"unsupported_content_type:{content_type}"}
            html = body.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
            return {
                "source_url": response.geturl(), "requested_url": canonical_url, "retrieved_at": retrieved_at,
                "status": "observed", "content_sha256": hashlib.sha256(body).hexdigest(),
                "html": html, "readable_text": extract_web_snapshot(html),
            }
    except HTTPError as error:
        return {"source_url": canonical_url, "retrieved_at": retrieved_at, "status": "retrieval_failed", "error_class": f"http_{error.code}"}
    except (URLError, TimeoutError):
        return {"source_url": canonical_url, "retrieved_at": retrieved_at, "status": "retrieval_failed", "error_class": "connection_failed"}

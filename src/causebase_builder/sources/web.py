"""Small deterministic web-snapshot text extractor for evidence review."""

from __future__ import annotations

from html.parser import HTMLParser


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

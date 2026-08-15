"""Bounded, private-first website syntax extraction for evidence review."""
from __future__ import annotations

import hashlib
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

ROLE_TERMS = {
    "about": ("about", "who we are", "our story"),
    "activities": ("what we do", "our work", "services", "activities"),
    "programs": ("program", "projects", "focus areas"),
    "participation": ("volunteer", "get involved", "join us", "donate"),
    "events": ("events", "what's on", "whats on"),
    "governance": ("governance", "board", "annual report"),
    "news": ("news", "latest", "media", "stories"),
    "contact": ("contact", "locations", "find us"),
}
TRANSIENT_ROLES = {"events", "news", "participation"}


class _PageParser(HTMLParser):
    ignored = {"script", "style", "nav", "footer", "header", "noscript"}
    def __init__(self) -> None:
        super().__init__(); self.ignored_depth=0; self.title=[]; self.headings=[]; self.blocks=[]; self.links=[]; self._tag=None; self._buffer=[]; self._href=None; self._link_text=[]
    def handle_starttag(self, tag, attrs) -> None:
        if tag in self.ignored: self.ignored_depth+=1
        if tag in {"title","h1","h2","h3","p","li"}: self._tag=tag; self._buffer=[]
        if tag == "a": self._href=dict(attrs).get("href"); self._link_text=[]
    def handle_data(self, data) -> None:
        if self.ignored_depth: return
        if self._tag: self._buffer.append(data)
        if self._href: self._link_text.append(data)
    def handle_endtag(self, tag) -> None:
        if tag in self.ignored and self.ignored_depth: self.ignored_depth-=1
        if tag == self._tag:
            value=" ".join(" ".join(self._buffer).split())
            if value:
                if tag == "title": self.title.append(value)
                elif tag.startswith("h"): self.headings.append({"text":value,"selector":tag})
                else: self.blocks.append({"text":value,"selector":tag})
            self._tag=None; self._buffer=[]
        if tag == "a" and self._href:
            label=" ".join(" ".join(self._link_text).split())
            self.links.append({"href":self._href,"label":label,"selector":"a"}); self._href=None; self._link_text=[]


def classify_role(url: str, label: str = "") -> str:
    haystack=f"{url} {label}".casefold()
    for role, terms in ROLE_TERMS.items():
        if any(term in haystack for term in terms): return role
    return "homepage"


def discover_pages(html: str, base_url: str, *, limit: int = 9) -> list[dict]:
    """Select at most one same-origin URL per governed page role."""
    parser=_PageParser(); parser.feed(html); base=urlparse(base_url); found={"homepage":base_url}
    for link in parser.links:
        url=urljoin(base_url, link["href"])
        parsed=urlparse(url)
        if parsed.scheme not in {"http", "https"} or parsed.netloc != base.netloc: continue
        role=classify_role(url, link["label"])
        if role not in found: found[role]=url
        if len(found)>=limit: break
    return [{"url":url,"page_role":role,"stable_class":"transient" if role in TRANSIENT_ROLES else "stable"} for role,url in found.items()]


def normalize_snapshot(html: str, *, requested_url: str, final_url: str | None = None, retrieved_at: str | None = None, page_role: str | None = None) -> dict:
    parser=_PageParser(); parser.feed(html); final_url=final_url or requested_url; role=page_role or classify_role(final_url)
    links=[]
    for link in parser.links:
        label=link["label"].casefold()
        links.append({**link,"url":urljoin(final_url,link["href"]),"link_role":"potential_action" if any(word in label for word in ("donate","volunteer","join","register","sign up","apply")) else "evidence_navigation","action_url_assigned":False})
    return {"requested_url":requested_url,"final_url":final_url,"retrieved_at":retrieved_at,"status":"observed","content_type":"text/html","content_sha256":hashlib.sha256(html.encode("utf-8")).hexdigest(),"page_role":role,"stable_class":"transient" if role in TRANSIENT_ROLES else "stable","title":" ".join(parser.title),"headings":parser.headings,"substantive_blocks":parser.blocks,"links":links,"extraction_method":"deterministic_html_parser_v2","warnings":[]}


def source_observation_candidates(page: dict) -> list[dict]:
    """Return review candidates only; this function never assigns public fields."""
    categories={"activities":("we do","services","support","advocacy","work"),"beneficiaries":("for ","communities","people","families","children"),"programs":("program","project","initiative"),"participation":("volunteer","donate","join","get involved"),"geography":("australia","victoria","queensland","new south wales","national")}
    candidates=[]
    for block in page["substantive_blocks"]:
        text=block["text"]
        for domain, markers in categories.items():
            if any(marker in text.casefold() for marker in markers):
                candidates.append({"domain":domain,"source_text":text,"source_location":block["selector"],"source_url":page["final_url"],"page_role":page["page_role"],"stable_class":page["stable_class"],"claim_basis":"direct_source_text","extraction_method":page["extraction_method"],"review_status":"review_required","warnings":["not_a_public_claim"]})
                break
    return candidates

"""Private, deterministic preparation for Knowledge Validation v1.

This module turns the bounded Evidence Engine output into review material.  It
does not synthesise cards, alter a taxonomy, make a release, or turn model
output into a human decision.  Its output directory is deliberately a private
runtime/staging location.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


REVIEW_VERSION = "knowledge-validation-v1"
HUMAN_OUTCOMES = ("ACCEPT", "EDIT", "REJECT", "WRONG_DOMAIN", "INSUFFICIENT", "IDENTITY_BLOCKED", "ADDITIVITY_BLOCKED")
DOMAINS = ("activities", "beneficiaries", "geography", "programs", "participation", "opportunities", "self_description", "fundraising", "identity_sensitive")


class ReviewDecision(BaseModel):
    """A human decision.  A model result is intentionally not this type."""

    case_id: str
    outcome: Literal["ACCEPT", "EDIT", "REJECT", "WRONG_DOMAIN", "INSUFFICIENT", "IDENTITY_BLOCKED", "ADDITIVITY_BLOCKED"]
    rationale: str | None = None
    editor_note: str | None = None
    decision_authority: Literal["human_governed"] = "human_governed"


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _edge_labels(candidate: dict[str, Any]) -> list[str]:
    text = candidate["source_text"].casefold()
    labels = []
    if any(word in text for word in ("©", "all rights", "acknowledge the traditional", "abn:", "tax deductible", "donate now")):
        labels.append("boilerplate_trap")
    if any(word in text for word in ("committed", "dedicated", "promise", "passion", "driving change", "empowers")):
        labels.append("organisation_rhetoric")
    if candidate["domain"] in {"activities", "participation"} or any(word in text for word in ("volunteer", "join us", "get involved")):
        labels.append("activity_participation_boundary")
    if candidate["domain"] == "beneficiaries": labels.append("beneficiary_ambiguity")
    if candidate["domain"] == "geography": labels.append("geography_ambiguity")
    if candidate["domain"] == "programs": labels.append("program_organisation_boundary")
    if candidate.get("stable_class") == "transient": labels.append("transient_evidence")
    return labels or ["straightforward_candidate"]


def _question(candidate: dict[str, Any], labels: list[str]) -> str:
    domain = candidate["domain"]
    if "boilerplate_trap" in labels:
        return "Is this evidence for the proposed observation, rather than footer, acknowledgement, donation or other boilerplate?"
    if "organisation_rhetoric" in labels:
        return "Does this support an observable, bounded proposition rather than organisational rhetoric or aspiration?"
    if domain == "activities": return "Does this state an activity actually undertaken, at a defensible level of specificity?"
    if domain == "beneficiaries": return "Does this identify a beneficiary group rather than an audience, supporter or incidental person?"
    if domain == "geography": return "Does this establish where activity occurs, rather than a contact, venue or broad rhetorical reference?"
    if domain == "programs": return "Is this a distinct program, rather than the organisation, a campaign or a generic activity?"
    if domain == "participation": return "Does this evidence a participation mode without treating a potential action link as a verified opportunity?"
    return "Is the proposed domain and claim basis supported by this exact excerpt?"


def flatten_candidates(pilot: dict[str, Any], golden: dict[str, Any]) -> list[dict[str, Any]]:
    subject_by_case = {item["case_id"]: item.get("causebase_id") for item in golden.get("cases", [])}
    rows = []
    for web in pilot.get("web", []):
        for candidate in web.get("candidates", []):
            row = dict(candidate)
            row["pilot_case_id"] = web["case_id"]
            row["causebase_id"] = subject_by_case.get(web["case_id"])
            row["source_evidence_hash"] = canonical_hash({key: row.get(key) for key in ("source_url", "source_location", "source_text")})
            row["edge_labels"] = _edge_labels(row)
            row["candidate_id"] = "kv1-" + canonical_hash({key: row.get(key) for key in ("pilot_case_id", "domain", "source_evidence_hash")})[:12]
            rows.append(row)
    return sorted(rows, key=lambda item: (item["pilot_case_id"], item["domain"], item["source_evidence_hash"]))


def inventory(rows: list[dict[str, Any]]) -> dict[str, Any]:
    duplicate_groups = defaultdict(list)
    for row in rows:
        duplicate_groups[(row["domain"], " ".join(row["source_text"].casefold().split()))].append(row["candidate_id"])
    def counts(key: str) -> dict[str, int]: return dict(sorted(Counter(str(row.get(key) or "unknown") for row in rows).items()))
    return {
        "candidate_count": len(rows),
        "by_subject": counts("causebase_id"), "by_pilot_case": counts("pilot_case_id"),
        "by_domain": counts("domain"), "by_page_role": counts("page_role"), "by_stability": counts("stable_class"),
        "by_extraction_route": counts("extraction_method"), "by_claim_basis": counts("claim_basis"),
        "source_type": {"retained_organisation_website_snapshot": len(rows)},
        "evidence_quality": {"direct_text_unadjudicated": len(rows)},
        "duplicate_status": {"unique": sum(len(value) == 1 for value in duplicate_groups.values()), "near_or_exact_duplicate_groups": sum(len(value) > 1 for value in duplicate_groups.values())},
        "missing_candidate_domains": [domain for domain in DOMAINS if domain not in {row["domain"] for row in rows}],
    }


def select_review_sample(rows: list[dict[str, Any]], *, target: int = 48) -> list[dict[str, Any]]:
    """Stable stratified selection, favouring decision-changing risk cases.

    At least one case from every available domain, pilot subject and edge class
    is taken before broadening the sample.  This is intentionally not random.
    """
    if not 1 <= target <= 60: raise ValueError("review target must be between 1 and 60")
    selected: dict[str, dict[str, Any]] = {}
    ordered = sorted(rows, key=lambda item: (item["candidate_id"]))
    strata = [
        lambda item: item["domain"], lambda item: item["pilot_case_id"],
        lambda item: item["page_role"], lambda item: item["stable_class"],
        lambda item: item["edge_labels"][0],
    ]
    for keyer in strata:
        for key in sorted({keyer(item) for item in ordered}):
            match = next((item for item in ordered if keyer(item) == key and item["candidate_id"] not in selected), None)
            if match: selected[match["candidate_id"]] = match
            if len(selected) >= target: break
        if len(selected) >= target: break
    # A round-robin across domain and case stops the abundant noisy categories
    # from consuming the packet.
    while len(selected) < min(target, len(ordered)):
        before = len(selected)
        for domain in sorted({item["domain"] for item in ordered}):
            for case in sorted({item["pilot_case_id"] for item in ordered}):
                match = next((item for item in ordered if item["domain"] == domain and item["pilot_case_id"] == case and item["candidate_id"] not in selected), None)
                if match: selected[match["candidate_id"]] = match
                if len(selected) >= target: break
            if len(selected) >= target: break
        if len(selected) == before: break
    result = []
    for item in sorted(selected.values(), key=lambda row: row["candidate_id"]):
        result.append({
            "case_id": item["candidate_id"], "causebase_id": item["causebase_id"], "domain": item["domain"],
            "source_url": item["source_url"], "source_page_role": item["page_role"], "source_excerpt": item["source_text"],
            "selector_or_location": item["source_location"], "candidate_structured_observation": {"domain": item["domain"], "text": item["source_text"]},
            "claim_basis_proposed": item["claim_basis"], "extraction_method": item["extraction_method"],
            "freshness_or_stability": item["stable_class"], "source_evidence_hash": item["source_evidence_hash"],
            "alternative_interpretation": "; ".join(item["edge_labels"]), "reviewer_question": _question(item, item["edge_labels"]),
        })
    return result


def automation_policy(decisions: list[ReviewDecision], sample: list[dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    """Compute separately by domain; never auto-promote without human gold."""
    grouped: dict[str, list[ReviewDecision]] = defaultdict(list)
    domains_by_case = {item["case_id"]: item["domain"] for item in sample or []}
    for item in decisions:
        domain = domains_by_case.get(item.case_id, "unresolved")
        grouped[domain].append(item)
    result = {}
    for domain in DOMAINS:
        outcomes = grouped.get(domain, [])
        accepts = sum(item.outcome == "ACCEPT" for item in outcomes)
        reviewed = len(outcomes)
        result[domain] = {
            "reviewed": reviewed,
            "accepts": accepts,
            "policy": "HUMAN REVIEW" if outcomes else "NOT READY",
            "reason": (
                "Human decisions are present, but the bounded sample is insufficient to authorise automation; no domain is auto-promotable."
                if reviewed else
                "No human-adjudicated evidence exists for this domain; it is not ready."
            ),
        }
    return result


def score_decisions(sample: list[dict[str, Any]], decisions: list[ReviewDecision]) -> dict[str, dict[str, Any]]:
    """Resolve human labels against their immutable review case and score by domain."""
    known = {item["case_id"] for item in sample}
    unknown = sorted({item.case_id for item in decisions} - known)
    if unknown: raise ValueError(f"decisions refer to unknown review cases: {unknown}")
    return automation_policy(decisions, sample)


def prepare(*, pilot_path: Path, golden_path: Path, output_dir: Path, target: int = 48) -> dict[str, Any]:
    pilot = json.loads(pilot_path.read_text(encoding="utf-8")); golden = json.loads(golden_path.read_text(encoding="utf-8"))
    rows = flatten_candidates(pilot, golden); sample = select_review_sample(rows, target=target)
    result = {"version": REVIEW_VERSION, "inputs": {"pilot_sha256": hashlib.sha256(pilot_path.read_bytes()).hexdigest(), "golden_sha256": hashlib.sha256(golden_path.read_bytes()).hexdigest()}, "inventory": inventory(rows), "review_sample": sample, "review_decision_schema": ReviewDecision.model_json_schema(), "automation_policy_pre_human_gate": automation_policy([], sample), "model_run": {"status": "not_run", "label": "No model result; models cannot supply human gold."}}
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "knowledge-validation-v1.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "semantic-review-decisions.json").write_text("[]\n", encoding="utf-8")
    lines = ["# Knowledge Validation v1 — human review", "", "Private, review-only packet. No candidate is a public claim.", "", f"- Candidates: {len(rows)}; deterministic stratified cases: {len(sample)}.", "- Outcomes: ACCEPT, EDIT, REJECT, WRONG_DOMAIN, INSUFFICIENT, IDENTITY_BLOCKED, ADDITIVITY_BLOCKED.", "", "## Semantic adjudication cases"]
    for item in sample:
        lines.extend([f"### {item['case_id']} — {item['domain']}", f"- Subject: `{item['causebase_id'] or 'unbound/review-only'}`", f"- Evidence: {item['source_url']} ({item['source_page_role']}; {item['selector_or_location']})", f"- Excerpt: {item['source_excerpt']}", f"- Question: {item['reviewer_question']}", ""])
    (output_dir / "HUMAN_REVIEW_PACKAGE.md").write_text("\n".join(lines), encoding="utf-8")
    return result

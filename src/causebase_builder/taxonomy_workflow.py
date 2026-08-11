"""Durable human-governed taxonomy review workflow.

PREPARE and VALIDATE are deterministic and non-mutating.  MODEL-REVIEW is
optional advisory evidence, deliberately separate from human decision records.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .models import CauseBaseCard
from .openai_client import estimate_response_cost, responses_create
from .taxonomy_review import DIMENSIONS, _derived_text, _term_dimension, corpus_diagnostics

WORKFLOW_VERSION = "1.0"
DECISIONS = ("approve", "reject", "defer", "watch", "request_more_evidence", "modify")


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class HumanDecision(BaseModel):
    decision_id: str
    review_id: str
    decision_date: date
    taxonomy_baseline_version: str
    pressure_ids: list[str] = Field(min_length=1)
    disposition: Literal["approve", "reject", "defer", "watch", "request_more_evidence", "modify"]
    approved_semantic_decision: str
    rationale: str
    definitions_and_boundaries: list[str] = Field(default_factory=list)
    important_exclusions: list[str] = Field(default_factory=list)
    representative_case_ids: list[str] = Field(default_factory=list)
    migration_implications: str
    decision_authority: str = "human_governed"
    resulting_taxonomy_version: str | None = None
    implementation_commits: list[str] = Field(default_factory=list)


def _load(corpus_path: Path, taxonomy_path: Path) -> tuple[list[CauseBaseCard], dict[str, Any]]:
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    taxonomy = json.loads(taxonomy_path.read_text(encoding="utf-8"))
    cards = [CauseBaseCard.model_validate(item) for item in corpus["entities"]]
    if taxonomy.get("taxonomy_id") != "causebase" or taxonomy.get("version") != "0.1-phase2a":
        raise ValueError("workflow demonstration requires frozen CauseBase 0.1-phase2a")
    return cards, taxonomy


def _builder_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return None


def _case(card: CauseBaseCard, why: str) -> dict[str, Any]:
    return {"causebase_id": card.causebase_id, "why_diagnostic": why, "derived": {
        "summary": _derived_text(card, 480), "activities": card.activities, "beneficiaries": card.beneficiaries,
        "participation_modes": card.participation_modes, "geography": card.geography,
        "current_causebase_classifications": [x.term_id for x in card.classifications if x.taxonomy_id == "causebase"],
    }}


def _representative_cases(cards: list[CauseBaseCard], taxonomy: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    """Stable bounded selection: positives, rich unassigned dimension cases, and sparse evidence cases."""
    selected: dict[str, dict[str, Any]] = {}
    native = {term["term_id"] for term in taxonomy["terms"]}
    for term in sorted(native):
        members = [card for card in sorted(cards, key=lambda x: x.causebase_id) if any(x.taxonomy_id == "causebase" and x.term_id == term for x in card.classifications)]
        for card in members[:limit]: selected.setdefault(card.causebase_id, _case(card, f"positive example for {term}"))
    for dimension in DIMENSIONS:
        missing = [card for card in sorted(cards, key=lambda x: x.causebase_id) if (card.activities or card.beneficiaries or card.participation_modes) and not any(_term_dimension(x.term_id) == dimension for x in card.classifications if x.taxonomy_id == "causebase")]
        for card in missing[:limit]: selected.setdefault(card.causebase_id, _case(card, f"rich evidence without {dimension} assignment"))
    sparse = [card for card in sorted(cards, key=lambda x: x.causebase_id) if not (card.activities or card.beneficiaries or card.participation_modes)]
    for card in sparse[:limit]: selected.setdefault(card.causebase_id, _case(card, "sparse descriptive-evidence boundary case"))
    return list(selected.values())[:40]


def _pressure_signals(cards: list[CauseBaseCard]) -> dict[str, Any]:
    unmapped: Counter[tuple[str, str]] = Counter(); ambiguities: Counter[tuple[str, tuple[str, ...]]] = Counter()
    coverage = Counter()
    for card in cards:
        signals = card.taxonomy_maintenance_signals
        if signals is None:
            coverage["signals_not_present_on_historical_card"] += 1; continue
        coverage["signals_available"] += 1
        for item in signals.unmapped_concepts: unmapped[(item.dimension, item.concept_phrase)] += 1
        for item in signals.taxonomy_ambiguities: ambiguities[(item.dimension, tuple(sorted(item.candidate_term_ids)))] += 1
    return {"coverage": dict(coverage), "recurring_unmapped_concepts": [{"dimension": d, "concept_phrase": p, "count": n} for (d,p),n in sorted(unmapped.items(), key=lambda x:(-x[1],x[0]))], "recurring_ambiguities": [{"dimension": d, "candidate_term_ids": list(t), "count": n} for (d,t),n in sorted(ambiguities.items(), key=lambda x:(-x[1],x[0]))]}


def _previous_review_delta(previous_review: Path | None, current: dict[str, Any]) -> dict[str, Any] | None:
    """Compare only prior workflow packets; historical review schemas stay immutable."""
    if previous_review is None:
        return None
    source = previous_review / "review-summary.json" if previous_review.is_dir() else previous_review
    try:
        prior = json.loads(source.read_text(encoding="utf-8")).get("review_summary", {})
    except (OSError, json.JSONDecodeError):
        return {"reference": str(previous_review), "status": "unavailable_or_historical_schema"}
    if prior.get("review_schema_version") != WORKFLOW_VERSION:
        return {"reference": str(previous_review), "status": "historical_schema_not_compared"}
    return {"reference": str(previous_review), "status": "compared", "subject_count_delta": current["subject_count"] - prior.get("subject_count", 0), "term_count_delta": current["current_taxonomy"]["term_count"] - prior.get("current_taxonomy", {}).get("term_count", 0)}


def prepare_review(*, corpus_path: Path, taxonomy_path: Path, output_dir: Path, similarities_path: Path | None = None, previous_review: Path | None = None) -> dict[str, Any]:
    cards, taxonomy = _load(corpus_path, taxonomy_path)
    similarities = json.loads(similarities_path.read_text(encoding="utf-8")) if similarities_path and similarities_path.exists() else None
    diagnostics = corpus_diagnostics(cards, taxonomy, similarities)
    source = {"corpus_sha256": hashlib.sha256(corpus_path.read_bytes()).hexdigest(), "taxonomy_sha256": hashlib.sha256(taxonomy_path.read_bytes()).hexdigest(), "similarities_sha256": hashlib.sha256(similarities_path.read_bytes()).hexdigest() if similarities_path and similarities_path.exists() else None}
    review_id = f"tr-{cards[0].dataset_version if cards else 'empty'}-{canonical_hash(source)[:12]}"
    summary = {"review_id": review_id, "review_schema_version": WORKFLOW_VERSION, "generated_at": datetime.now(timezone.utc).isoformat(), "corpus_version": cards[0].dataset_version if cards else None, "subject_count": len(cards), "taxonomy_id": taxonomy["taxonomy_id"], "taxonomy_version": taxonomy["version"], "taxonomy_hash": source["taxonomy_sha256"], "builder_commit": _builder_commit(), "input_hashes": source, "current_taxonomy": {"dimensions": taxonomy["dimensions"], "term_count": len(taxonomy["terms"]), "terms": taxonomy["terms"], "status": taxonomy.get("status")}, "term_diagnostics": diagnostics, "dimension_diagnostics": {"rich_subjects_missing_dimension_assignment": diagnostics["rich_subjects_missing_dimension_assignment"], "low_vocabulary_coverage_dimensions": diagnostics["low_vocabulary_coverage_dimensions"]}, "taxonomy_pressure_signals": _pressure_signals(cards), "representative_cases": _representative_cases(cards, taxonomy), "review_questions": ["Do broad local/geography and organisation-character co-occurrences reflect useful independent facets or classifier convention?", "Which rich but dimension-unassigned cases need human boundary inspection?", "Does sparse descriptive evidence require coverage investment before taxonomy expansion?"], "historical_review_references": [str(previous_review)] if previous_review else []}
    summary["change_since_previous_review"] = _previous_review_delta(previous_review, summary)
    result = {"review_summary": summary}
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "review-summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "decision-record.json").write_text("[]\n", encoding="utf-8")
    (output_dir / "decisions.md").write_text("# Human taxonomy decisions\n\nNo decisions recorded. Model outputs and pressure signals are advisory only.\n", encoding="utf-8")
    (output_dir / "migration-report.md").write_text("# Migration report\n\nNo approved taxonomy change has been implemented; validation is not yet applicable.\n", encoding="utf-8")
    lines=[f"# Taxonomy review {review_id}","", "Deterministic PREPARE packet. It contains pressure and questions, not automated change proposals.","",f"- Corpus: {len(cards)} cards, `{cards[0].dataset_version if cards else 'none'}`.",f"- Baseline: `{taxonomy['taxonomy_id']}` `{taxonomy['version']}`, {len(taxonomy['terms'])} terms.",f"- Bounded representative cases: {len(result['review_summary']['representative_cases'])}.","", "## Review questions"] + [f"- {x}" for x in result['review_summary']['review_questions']]
    (output_dir / "pressure-report.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    return result


def render_decisions(*, decision_record_path: Path, output_path: Path) -> list[HumanDecision]:
    """Render only validated human decisions; it never implements a taxonomy."""
    decisions = [HumanDecision.model_validate(x) for x in json.loads(decision_record_path.read_text(encoding="utf-8"))]
    lines = ["# Human taxonomy decisions", ""]
    for item in decisions:
        lines.extend([f"## {item.decision_id}: {item.disposition}", "", f"- Review: `{item.review_id}`", f"- Pressure signals: {', '.join(item.pressure_ids)}", f"- Semantic decision: {item.approved_semantic_decision}", f"- Rationale: {item.rationale}", f"- Migration: {item.migration_implications}", ""])
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return decisions


def model_review(*, review_summary_path: Path, output_dir: Path, model: str, reasoning_effort: str = "high") -> dict[str, Any]:
    """Run an explicitly optional, compact, advisory model critique.

    This function does not read the corpus, write decisions, or mutate the
    PREPARE packet.  API response IDs are retained only in private telemetry.
    """
    prepared = json.loads(review_summary_path.read_text(encoding="utf-8"))["review_summary"]
    advisory_input = {key: prepared[key] for key in ("review_id", "corpus_version", "taxonomy_version", "current_taxonomy", "term_diagnostics", "dimension_diagnostics", "taxonomy_pressure_signals", "representative_cases", "review_questions")}
    schema = {"type": "json_schema", "name": "taxonomy_review_advisory", "strict": True, "schema": {"type": "object", "additionalProperties": False, "properties": {"advisory_findings": {"type": "array", "items": {"type": "string"}}, "counterexamples": {"type": "array", "items": {"type": "string"}}, "limitations": {"type": "array", "items": {"type": "string"}}, "human_questions": {"type": "array", "items": {"type": "string"}}}, "required": ["advisory_findings", "counterexamples", "limitations", "human_questions"]}}
    instruction = "You are an advisory taxonomy reviewer. Do not make or implement decisions, invent canonical terms, use ACNC categories, or treat pressure as proof. Critique the compact deterministic packet and return only bounded findings and questions.\n\n" + json.dumps(advisory_input, ensure_ascii=False, sort_keys=True)
    response = responses_create(model=model, input_text=instruction, text_format=schema, max_output_tokens=1_800, reasoning={"effort": reasoning_effort})
    content = json.loads(response.output_text)
    output_dir.mkdir(parents=True, exist_ok=True)
    result = {"model_review": {"review_id": prepared["review_id"], "advisory_only": True, "model": response.model, "reasoning_effort": reasoning_effort, "input_hash": canonical_hash(advisory_input), "findings": content}}
    (output_dir / "model-review-advisory.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    telemetry = {"response_id": response.response_id, "model": response.model, "status": response.status, "input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens, "total_tokens": response.usage.total_tokens, "estimated_cost_usd": str(estimate_response_cost(response.model, response.usage) or "unknown")}
    (output_dir / "model-review-private-telemetry.json").write_text(json.dumps(telemetry, indent=2), encoding="utf-8")
    return result


def validate_implemented_change(*, corpus_path: Path, baseline_taxonomy_path: Path, candidate_taxonomy_path: Path, decision_record_path: Path, output_path: Path) -> dict[str, Any]:
    cards, baseline = _load(corpus_path, baseline_taxonomy_path); candidate=json.loads(candidate_taxonomy_path.read_text(encoding="utf-8")); decisions=[HumanDecision.model_validate(x) for x in json.loads(decision_record_path.read_text(encoding="utf-8"))]
    before={x["term_id"] for x in baseline["terms"]}; after={x["term_id"] for x in candidate["terms"]}
    base_terms={x["term_id"]: x for x in baseline["terms"]}; candidate_terms={x["term_id"]: x for x in candidate["terms"]}
    changed=sorted(term for term in before & after if base_terms[term] != candidate_terms[term])
    result={"validation": {"schema_version": WORKFLOW_VERSION, "corpus_version": cards[0].dataset_version if cards else None, "baseline_version": baseline["version"], "candidate_version": candidate.get("version"), "terms_added": sorted(after-before), "terms_removed": sorted(before-after), "terms_definition_or_boundary_changed": changed, "affected_subject_counts": {term: sum(any(x.taxonomy_id=="causebase" and x.term_id==term for x in card.classifications) for card in cards) for term in sorted(before|after)}, "decision_ids": [x.decision_id for x in decisions], "decision_dispositions": {x.decision_id: x.disposition for x in decisions}, "non_mutating": True, "reclassification_required_for_current_assignments": sorted(set(before-after) | set(changed)), "downstream_regeneration_requirements": ["card classifications", "semantic source text", "embeddings", "neighbours", "Viewer filters", "cross-taxonomy mappings"]}}
    output_path.parent.mkdir(parents=True,exist_ok=True); output_path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8"); return result

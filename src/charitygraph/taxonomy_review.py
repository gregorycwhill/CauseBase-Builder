"""Governed, non-mutating periodic review of the CauseBase vocabulary.

This module deliberately sits after card synthesis.  It cannot edit the
taxonomy file or card classifications: its only outputs are private review
artefacts for a human product decision.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .models import CauseBaseCard
from .openai_client import ApiResult, ApiUsage, estimate_synthesis_cost, responses_create


TAXONOMY_REVIEW_VERSION = "0.1"
TAXONOMY_REVIEW_PROMPT_VERSION = "taxonomy-review-0.1"
DIMENSIONS = (
    "cause_problem", "beneficiary", "activity", "approach", "participation",
    "geography", "organisational_character",
)
TERM_DIMENSIONS = {"cause": "cause_problem", "beneficiary": "beneficiary", "activity": "activity",
                   "approach": "approach", "participation": "participation", "geography": "geography",
                   "organisation": "organisational_character"}
OPERATIONS = ("add", "split", "merge", "refine", "deprecate")


class TaxonomyProposal(BaseModel):
    proposal_id: str
    operation: Literal["add", "split", "merge", "refine", "deprecate"]
    affected_term_ids: list[str] = Field(default_factory=list)
    proposed_term_ids: list[str] = Field(default_factory=list)
    proposed_terms: list["ProposedTermProfile"] = Field(default_factory=list)
    dimension: str
    rationale: str
    evidence_summary: str
    supporting_subject_count: int = Field(ge=0)
    representative_subject_ids: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    boundary_cases: list[str] = Field(default_factory=list)
    expected_discovery_value: str
    confidence: Literal["high", "medium", "low"]
    priority: Literal["HIGH", "MEDIUM", "WATCH"]
    downstream_impact: str
    recommendation: str


class ProposedTermProfile(BaseModel):
    """An unapproved definition draft, never a canonical taxonomy term."""

    term_id: str
    human_label: str
    dimension: str
    definition: str
    inclusion_guidance: str
    exclusion_boundary_guidance: str
    representative_positive_examples: list[str] = Field(default_factory=list)
    confusing_neighbour_term_ids: list[str] = Field(default_factory=list)
    status: Literal["proposed_add", "proposed_replacement", "retained_definition_draft"]
    taxonomy_version: str = "unapproved"


class TermAudit(BaseModel):
    term_id: str
    disposition: Literal[
        "retain", "retain_with_refinement", "split_candidate", "merge_candidate",
        "deprecate_candidate", "insufficient_evidence",
    ]
    rationale: str
    definition_or_boundary_guidance: str


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _term_dimension(term_id: str) -> str:
    return TERM_DIMENSIONS.get(term_id.split(".", 1)[0], "unknown")


def _derived_text(card: CauseBaseCard, limit: int = 600) -> str:
    """Use evidence-derived card text without identity or any taxonomy assertion."""
    parts = [card.causebase_summary]
    for label, values in (
        ("activities", card.activities), ("beneficiaries", card.beneficiaries),
        ("geography", card.geography), ("participation", card.participation_modes),
    ):
        if values:
            parts.append(f"{label}: " + "; ".join(values))
    text = " ".join(part.strip() for part in parts if part and part.strip())
    # A regulator name is not a classification, but masking it makes the blind
    # packet visibly incapable of using ACNC-labelled concepts as a seed.
    return text.replace("ACNC", "regulatory").replace("Australian Charities and Not-for-profits Commission", "regulatory source")[:limit]


def build_blind_discovery_input(cards: list[CauseBaseCard]) -> dict[str, Any]:
    """Create the taxonomy-blind pass-A representation.

    Intentionally absent: names, identifiers other than opaque CauseBase IDs,
    all classifications, taxonomy labels/IDs, ACNC fields, and cohort strata.
    """
    records = []
    for card in sorted(cards, key=lambda item: item.causebase_id):
        records.append({
            "causebase_id": card.causebase_id,
            "derived_description": _derived_text(card),
            "activities": card.activities,
            "beneficiaries": card.beneficiaries,
            "geography": card.geography,
            "participation_modes": card.participation_modes,
            "opportunity_descriptions": [f"{item.type}: {item.title}" for item in card.opportunities],
            "descriptive_evidence_available": bool(card.activities or card.beneficiaries or card.participation_modes or len(card.causebase_summary) >= 180),
        })
    result = {"corpus_size": len(records), "dimensions": list(DIMENSIONS), "records": records}
    assert_blind_discovery_input(result)
    return result


def assert_blind_discovery_input(packet: dict[str, Any]) -> None:
    """Fail closed when a caller accidentally gives Pass A a taxonomy or ACNC field."""
    forbidden_keys = {"classifications", "taxonomy", "term_id", "term_label", "legal_name", "display_name",
                      "external_identifiers", "acnc_classifications", "cohort_strata", "acnc_categories"}
    def walk(value: Any) -> None:
        if isinstance(value, dict):
            overlap = forbidden_keys & set(value)
            if overlap:
                raise ValueError(f"blind discovery input contains forbidden fields: {sorted(overlap)}")
            for child in value.values(): walk(child)
        elif isinstance(value, list):
            for child in value: walk(child)
    walk(packet)
    encoded = json.dumps(packet, ensure_ascii=False).lower()
    if "acnc-register" in encoded:
        raise ValueError("blind discovery input contains ACNC classification content")


def corpus_diagnostics(cards: list[CauseBaseCard], taxonomy: dict[str, Any], similarities: dict[str, Any] | None = None) -> dict[str, Any]:
    """Deterministic signals to focus review; none is an automatic decision rule."""
    taxonomy_terms = [term["term_id"] for term in taxonomy["terms"]]
    assignments: dict[str, list[CauseBaseCard]] = {term: [] for term in taxonomy_terms}
    pair_counts: Counter[tuple[str, str]] = Counter()
    dimension_no_assignment: dict[str, list[str]] = defaultdict(list)
    evidence_coverage: dict[str, Counter[str]] = {term: Counter() for term in taxonomy_terms}
    confidence: dict[str, Counter[str]] = {term: Counter() for term in taxonomy_terms}

    for card in sorted(cards, key=lambda item: item.causebase_id):
        native = sorted({item.term_id for item in card.classifications if item.taxonomy_id == taxonomy["taxonomy_id"] and item.term_id in assignments})
        present_dimensions = {_term_dimension(term) for term in native}
        for term in native:
            assignments[term].append(card)
            item = next(value for value in card.classifications if value.taxonomy_id == taxonomy["taxonomy_id"] and value.term_id == term)
            confidence[term][item.confidence or "unspecified"] += 1
            evidence_coverage[term]["with_evidence_ids" if item.evidence_ids else "without_evidence_ids"] += 1
        for index, left in enumerate(native):
            for right in native[index + 1:]: pair_counts[(left, right)] += 1
        rich = bool(card.activities or card.beneficiaries or card.participation_modes or len(card.causebase_summary) >= 220)
        if rich:
            for dimension in DIMENSIONS:
                if dimension not in present_dimensions:
                    dimension_no_assignment[dimension].append(card.causebase_id)

    total = max(len(cards), 1)
    terms = []
    for term in taxonomy_terms:
        members = assignments[term]
        count = len(members)
        probability = count / total
        information_bits = round(-__import__("math").log2(probability), 3) if probability else None
        terms.append({
            "term_id": term, "dimension": _term_dimension(term), "assigned_subject_count": count,
            "assigned_percent": round(100 * probability, 2), "information_bits_when_present": information_bits,
            "assigned_alone_count": sum(1 for card in members if len([x for x in card.classifications if x.taxonomy_id == taxonomy["taxonomy_id"]]) == 1),
            "representative_subject_ids": [card.causebase_id for card in members[:4]],
            "assignment_confidence_distribution": dict(sorted(confidence[term].items())),
            "classification_evidence_coverage_distribution": dict(sorted(evidence_coverage[term].items())),
        })
    cooccurrences = [
        {"term_ids": list(pair), "subject_count": count, "percent_of_smaller_term": round(100 * count / max(1, min(len(assignments[pair[0]]), len(assignments[pair[1]]))), 2)}
        for pair, count in pair_counts.items()
    ]
    cooccurrences.sort(key=lambda item: (-item["subject_count"], item["term_ids"]))
    return {
        "subject_count": len(cards), "terms": terms, "major_cooccurrences": cooccurrences[:30],
        "high_frequency_terms": [item["term_id"] for item in terms if item["assigned_percent"] >= 65],
        "rare_terms": [item["term_id"] for item in terms if item["assigned_subject_count"] <= 3],
        "low_vocabulary_coverage_dimensions": [dimension for dimension in DIMENSIONS if not any(item["dimension"] == dimension and item["assigned_subject_count"] for item in terms)],
        "rich_subjects_missing_dimension_assignment": {key: value[:30] for key, value in sorted(dimension_no_assignment.items())},
        "semantic_diversity": _semantic_diversity(similarities),
    }


def _semantic_diversity(similarities: dict[str, Any] | None) -> dict[str, Any]:
    if not similarities:
        return {"status": "not_available"}
    links = similarities.get("links", similarities.get("similarities", [])) if isinstance(similarities, dict) else []
    scores = [item.get("score") for item in links if isinstance(item, dict) and isinstance(item.get("score"), (int, float))]
    return {"status": "available", "link_count": len(scores), "mean_link_score": round(sum(scores) / len(scores), 4) if scores else None}


def _representative_examples(cards: list[CauseBaseCard], taxonomy: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    examples: dict[str, list[dict[str, str]]] = defaultdict(list)
    term_ids = {term["term_id"] for term in taxonomy["terms"]}
    for card in cards:
        for classification in card.classifications:
            if classification.taxonomy_id == taxonomy["taxonomy_id"] and classification.term_id in term_ids and len(examples[classification.term_id]) < 4:
                examples[classification.term_id].append({"causebase_id": card.causebase_id, "derived_description": _derived_text(card, 420)})
    return dict(examples)


def _blind_schema() -> dict[str, Any]:
    concept = {"type": "object", "additionalProperties": False, "properties": {
        "dimension": {"type": "string"}, "proposed_neutral_concept_label": {"type": "string"},
        "provisional_definition": {"type": "string"}, "inclusion_examples": {"type": "array", "items": {"type": "string"}},
        "exclusion_boundary_examples": {"type": "array", "items": {"type": "string"}},
        "approximate_supporting_subject_count": {"type": "integer"}, "representative_subject_ids": {"type": "array", "items": {"type": "string"}},
        "representative_evidence_phrases": {"type": "array", "items": {"type": "string"}}, "related_concepts": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]}, "discovery_value": {"type": "string"},
    }, "required": ["dimension", "proposed_neutral_concept_label", "provisional_definition", "inclusion_examples", "exclusion_boundary_examples", "approximate_supporting_subject_count", "representative_subject_ids", "representative_evidence_phrases", "related_concepts", "confidence", "discovery_value"]}
    return {"type": "json_schema", "name": "causebase_taxonomy_blind_discovery", "strict": True, "schema": {"type": "object", "additionalProperties": False, "properties": {"dimensions": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {"dimension": {"type": "string"}, "concepts": {"type": "array", "items": concept}}, "required": ["dimension", "concepts"]}}, "dimension_gaps": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {"description": {"type": "string"}, "supporting_subject_ids": {"type": "array", "items": {"type": "string"}}, "confidence": {"type": "string", "enum": ["high", "medium", "low"]}}, "required": ["description", "supporting_subject_ids", "confidence"]}}}, "required": ["dimensions", "dimension_gaps"]}}


def _critique_schema() -> dict[str, Any]:
    profile = {"type": "object", "additionalProperties": False, "properties": {"term_id": {"type": "string"}, "human_label": {"type": "string"}, "dimension": {"type": "string"}, "definition": {"type": "string"}, "inclusion_guidance": {"type": "string"}, "exclusion_boundary_guidance": {"type": "string"}, "representative_positive_examples": {"type": "array", "items": {"type": "string"}}, "confusing_neighbour_term_ids": {"type": "array", "items": {"type": "string"}}, "status": {"type": "string", "enum": ["proposed_add", "proposed_replacement", "retained_definition_draft"]}, "taxonomy_version": {"type": "string"}}, "required": ["term_id", "human_label", "dimension", "definition", "inclusion_guidance", "exclusion_boundary_guidance", "representative_positive_examples", "confusing_neighbour_term_ids", "status", "taxonomy_version"]}
    proposal = {"type": "object", "additionalProperties": False, "properties": {
        "proposal_id": {"type": "string"}, "operation": {"type": "string", "enum": list(OPERATIONS)}, "affected_term_ids": {"type": "array", "items": {"type": "string"}}, "proposed_term_ids": {"type": "array", "items": {"type": "string"}}, "proposed_terms": {"type": "array", "items": profile}, "dimension": {"type": "string"}, "rationale": {"type": "string"}, "evidence_summary": {"type": "string"}, "supporting_subject_count": {"type": "integer"}, "representative_subject_ids": {"type": "array", "items": {"type": "string"}}, "examples": {"type": "array", "items": {"type": "string"}}, "boundary_cases": {"type": "array", "items": {"type": "string"}}, "expected_discovery_value": {"type": "string"}, "confidence": {"type": "string", "enum": ["high", "medium", "low"]}, "priority": {"type": "string", "enum": ["HIGH", "MEDIUM", "WATCH"]}, "downstream_impact": {"type": "string"}, "recommendation": {"type": "string"},
    }, "required": ["proposal_id", "operation", "affected_term_ids", "proposed_term_ids", "proposed_terms", "dimension", "rationale", "evidence_summary", "supporting_subject_count", "representative_subject_ids", "examples", "boundary_cases", "expected_discovery_value", "confidence", "priority", "downstream_impact", "recommendation"]}
    audit = {"type": "object", "additionalProperties": False, "properties": {"term_id": {"type": "string"}, "disposition": {"type": "string", "enum": ["retain", "retain_with_refinement", "split_candidate", "merge_candidate", "deprecate_candidate", "insufficient_evidence"]}, "rationale": {"type": "string"}, "definition_or_boundary_guidance": {"type": "string"}}, "required": ["term_id", "disposition", "rationale", "definition_or_boundary_guidance"]}
    return {"type": "json_schema", "name": "causebase_taxonomy_critique", "strict": True, "schema": {"type": "object", "additionalProperties": False, "properties": {"proposals": {"type": "array", "items": proposal}, "term_audit": {"type": "array", "items": audit}, "unchanged_terms": {"type": "array", "items": {"type": "string"}}, "unresolved_questions": {"type": "array", "items": {"type": "string"}}}, "required": ["proposals", "term_audit", "unchanged_terms", "unresolved_questions"]}}


def _acnc_schema() -> dict[str, Any]:
    item = {"type": "string"}
    return {"type": "json_schema", "name": "causebase_taxonomy_acnc_annex", "strict": True, "schema": {"type": "object", "additionalProperties": False, "properties": {"apparent_overlap": {"type": "array", "items": item}, "causebase_only_distinctions": {"type": "array", "items": item}, "acnc_categories_causebase_does_not_need": {"type": "array", "items": item}, "superficially_similar_but_different": {"type": "array", "items": item}, "accidental_convergence": {"type": "array", "items": item}}, "required": ["apparent_overlap", "causebase_only_distinctions", "acnc_categories_causebase_does_not_need", "superficially_similar_but_different", "accidental_convergence"]}}


def blind_discovery_prompt(packet: dict[str, Any]) -> str:
    return """You are conducting Pass A of a governed CauseBase taxonomy review. The supplied records are deliberately taxonomy-blind and do not contain regulator classifications. Discover recurring, discriminative evidence-grounded concepts only; do not infer from organisation names, familiar charity-sector labels, or missing data. Do not maximise term count. Long-tail specificity belongs in rich descriptions, embeddings and future evidence, not necessarily taxonomy. Null is valid. Organise findings only under the supplied seven dimensions; report DIMENSION_GAP only for a serious recurring structural failure, never invent a dimension for convenience. Keep cause/problems, beneficiaries, activities, approaches, participation opportunities, geography scope and organisational character distinct. Return no proposal to alter any taxonomy: there is no current taxonomy in this pass. Be compact: report at most three genuinely recurring concepts per dimension, with one short inclusion and one short boundary example each.

TAXONOMY-BLIND DERIVED CORPUS:
""" + json.dumps(packet, ensure_ascii=False)


def critique_prompt(packet: dict[str, Any]) -> str:
    return """You are conducting Pass B of a governed CauseBase taxonomy review. Pass A is already complete. Compare the independently discovered concepts to the frozen current taxonomy and diagnostics. Propose a compact, ranked set only where recurring evidence supports a useful change. Do not maximise term count, reproduce regulatory categories, or treat frequency/correlation as an automatic rule. Assess every current term exactly once. A retained/new concept needs a definition and boundary guidance; do not silently change a material meaning. For every proposed add, replacement or material refinement, supply an unapproved `proposed_terms` definition profile with inclusion/exclusion guidance and confusing neighbours; never use label-only terms. Valid operations are add, split, merge, refine and deprecate. Proposals are recommendations for a human only: never alter a taxonomy or a card classification. Include a realistic downstream migration impact.

Quality limits: return at most eight proposals total and no more than four HIGH proposals; use MEDIUM/WATCH or no proposal where corpus evidence is immature. Every support count must be no more than the supplied corpus size and every representative ID must be an actual supplied CauseBase ID. Organisational character must not restate legal or regulatory status (including registration); geography must not create a term merely from an address or generic Australia-wide record. Do not treat an absent current term assignment as proof a new term is warranted.

PASS B PACKET:
""" + json.dumps(packet, ensure_ascii=False)


def acnc_comparison_prompt(packet: dict[str, Any]) -> str:
    return """This is a post-hoc ACNC comparison annex. Independent CauseBase discovery and critique are already frozen in the supplied packet. Do not revise them to align with ACNC. Describe overlap, useful CauseBase-only distinctions, ACNC regulatory distinctions CauseBase does not need, superficially similar labels with different meanings, and any accidental convergence. ACNC coverage is never evidence that CauseBase needs a term.

POST-HOC COMPARISON PACKET:
""" + json.dumps(packet, ensure_ascii=False)


def _structured_call(model: str, prompt: str, schema: dict[str, Any], max_output_tokens: int) -> tuple[dict[str, Any], dict[str, Any]]:
    # Long structured review responses need a larger response window, but do
    # not retry automatically: a retry after an uncertain network timeout can
    # duplicate a costly governed call. A human/operator may rerun explicitly.
    result: ApiResult = responses_create(
        model=model, input_text=prompt, text_format=schema, max_output_tokens=max_output_tokens,
        max_attempts=1, timeout_seconds=180,
    )
    if result.status not in {"completed", None}:
        raise ValueError(f"taxonomy review did not complete (status: {result.status})")
    try:
        return json.loads(result.output_text), {"response_id": result.response_id, "model": result.model, "input_tokens": result.usage.input_tokens, "output_tokens": result.usage.output_tokens, "estimated_cost_usd": str(estimate_synthesis_cost(result.usage)) if estimate_synthesis_cost(result.usage) is not None else None}
    except json.JSONDecodeError as error:
        raise ValueError("taxonomy review response was not valid structured JSON") from error


def _acnc_aggregate(cards: list[CauseBaseCard]) -> dict[str, int]:
    values: Counter[str] = Counter()
    for card in cards:
        for classification in card.classifications:
            if classification.taxonomy_id.startswith("acnc"):
                values[classification.term_label] += 1
    return dict(sorted(values.items()))


def _validate_proposal_semantics(proposals: list[TaxonomyProposal], cards: list[CauseBaseCard]) -> None:
    """Reject impossible or ungovernably broad LLM output before it is packaged."""
    if len(proposals) > 8:
        raise ValueError("taxonomy critique exceeded the compact eight-proposal limit")
    if sum(item.priority == "HIGH" for item in proposals) > 4:
        raise ValueError("taxonomy critique exceeded the four-HIGH-proposal limit")
    subject_ids = {card.causebase_id for card in cards}
    for proposal in proposals:
        if proposal.dimension not in DIMENSIONS:
            raise ValueError(f"proposal {proposal.proposal_id} has an invalid dimension")
        if proposal.supporting_subject_count > len(cards):
            raise ValueError(f"proposal {proposal.proposal_id} claims more subjects than the corpus contains")
        if not set(proposal.representative_subject_ids) <= subject_ids:
            raise ValueError(f"proposal {proposal.proposal_id} names an unknown representative subject")
        profiles = {item.term_id for item in proposal.proposed_terms}
        if not set(proposal.proposed_term_ids) <= profiles:
            raise ValueError(f"proposal {proposal.proposal_id} has label-only proposed terms")
        if any(item.dimension != proposal.dimension for item in proposal.proposed_terms):
            raise ValueError(f"proposal {proposal.proposal_id} has a term profile in another dimension")


def run_taxonomy_review(*, corpus_path: Path, taxonomy_path: Path, output_dir: Path, similarities_path: Path | None = None, model: str = "gpt-5-mini", reuse_blind_review: Path | None = None) -> dict[str, Any]:
    """Run bounded Pass A, Pass B and the strictly post-hoc ACNC annex.

    `output_dir` is intentionally caller-supplied so orchestration can place it
    under a private archive. The taxonomy path is opened read-only and never
    written by this function.
    """
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    cards = [CauseBaseCard.model_validate(item) for item in corpus["entities"]]
    taxonomy = json.loads(taxonomy_path.read_text(encoding="utf-8"))
    if taxonomy.get("version") != "0.1-phase2a":
        raise ValueError("first taxonomy review requires frozen baseline 0.1-phase2a")
    if len(taxonomy.get("dimensions", [])) != 7 or len(taxonomy.get("terms", [])) != 23:
        raise ValueError("taxonomy baseline is not the expected 7-dimension, 23-term snapshot")
    if output_dir.resolve() in {corpus_path.resolve().parent, taxonomy_path.resolve().parent}:
        raise ValueError("taxonomy review output must be a separate private directory")
    similarities = json.loads(similarities_path.read_text(encoding="utf-8")) if similarities_path and similarities_path.exists() else None
    blind_input = build_blind_discovery_input(cards)
    diagnostics = corpus_diagnostics(cards, taxonomy, similarities)
    if reuse_blind_review:
        previous = json.loads(reuse_blind_review.read_text(encoding="utf-8"))["taxonomy_review"]
        if previous.get("baseline_taxonomy_version") != taxonomy["version"] or previous.get("blind_input_hash") != _canonical_hash(blind_input):
            raise ValueError("reused blind discovery does not match this frozen baseline and corpus")
        blind = previous["blind_discovery"]
        blind_telemetry = {"response_id": None, "model": previous.get("model", model), "input_tokens": None, "output_tokens": None, "estimated_cost_usd": None, "reused_blind_discovery": True}
    else:
        blind, blind_telemetry = _structured_call(model, blind_discovery_prompt(blind_input), _blind_schema(), 20_000)
    critique_input = {"baseline_taxonomy": taxonomy, "blind_discovery": blind, "current_taxonomy_diagnostics": diagnostics, "representative_assigned_examples": _representative_examples(cards, taxonomy)}
    critique, critique_telemetry = _structured_call(model, critique_prompt(critique_input), _critique_schema(), 16_000)
    audits = [TermAudit.model_validate(item) for item in critique["term_audit"]]
    expected_terms = {item["term_id"] for item in taxonomy["terms"]}
    if {item.term_id for item in audits} != expected_terms or len(audits) != len(expected_terms):
        raise ValueError("taxonomy critique must audit every baseline term exactly once")
    proposals = [TaxonomyProposal.model_validate(item) for item in critique["proposals"]]
    if len({item.proposal_id for item in proposals}) != len(proposals):
        raise ValueError("taxonomy critique returned duplicate proposal IDs")
    _validate_proposal_semantics(proposals, cards)
    acnc_input = {"independent_blind_discovery": blind, "independent_proposals": [item.model_dump(mode="json") for item in proposals], "acnc_classification_frequency_after_independent_review": _acnc_aggregate(cards)}
    acnc_comparison, acnc_telemetry = _structured_call(model, acnc_comparison_prompt(acnc_input), _acnc_schema(), 4_000)
    generated_at = datetime.now(timezone.utc).isoformat()
    result = {
        "taxonomy_review": {
            "review_version": TAXONOMY_REVIEW_VERSION, "prompt_version": TAXONOMY_REVIEW_PROMPT_VERSION,
            "corpus_version": cards[0].dataset_version if cards else None, "corpus_subject_count": len(cards),
            "baseline_taxonomy_version": taxonomy["version"], "baseline_taxonomy_hash": _canonical_hash(taxonomy),
            "model": model, "generated_at": generated_at, "blind_input_hash": _canonical_hash(blind_input),
            "reused_blind_discovery": bool(reuse_blind_review),
            "critique_input_hash": _canonical_hash(critique_input), "acnc_comparison_input_hash": _canonical_hash(acnc_input),
            "blind_discovery": blind, "current_taxonomy_diagnostics": diagnostics,
            "proposals": [item.model_dump(mode="json") for item in proposals],
            "term_audit": [item.model_dump(mode="json") for item in audits], "unchanged_terms": critique["unchanged_terms"],
            "acnc_comparison": acnc_comparison, "unresolved_questions": critique["unresolved_questions"],
        }
    }
    telemetry = {"review_version": TAXONOMY_REVIEW_VERSION, "generated_at": generated_at, "calls": [blind_telemetry, critique_telemetry, acnc_telemetry]}
    telemetry["total_input_tokens"] = sum(item["input_tokens"] or 0 for item in telemetry["calls"])
    telemetry["total_output_tokens"] = sum(item["output_tokens"] or 0 for item in telemetry["calls"])
    telemetry["total_estimated_cost_usd"] = str(sum((Decimal(item["estimated_cost_usd"]) for item in telemetry["calls"] if item["estimated_cost_usd"] is not None), Decimal("0")))
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "taxonomy-review.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "taxonomy-review-private-telemetry.json").write_text(json.dumps(telemetry, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "taxonomy-review-report.md").write_text(render_review_report(result, telemetry), encoding="utf-8")
    return result


def render_review_report(result: dict[str, Any], telemetry: dict[str, Any]) -> str:
    review = result["taxonomy_review"]
    diagnostics = review["current_taxonomy_diagnostics"]
    proposals = review["proposals"]
    lines = ["# CauseBase Taxonomy Review v0.1", "", "**Private governed decision package.** This review proposes changes only; it does not modify the frozen taxonomy or any card classification.", "", "## Baseline and corpus", "", f"- Baseline: CauseBase taxonomy `{review['baseline_taxonomy_version']}` — 7 dimensions, 23 terms.", f"- Corpus: `{review['corpus_version']}` — {review['corpus_subject_count']} subjects.", f"- Model: `{review['model']}`; prompt `{review['prompt_version']}`.", "", "## Deterministic diagnostics", "", f"- High-frequency terms: {', '.join(diagnostics['high_frequency_terms']) or 'none'}.", f"- Rare terms (≤3 assigned subjects): {', '.join(diagnostics['rare_terms']) or 'none'}.", f"- Dimensions with no vocabulary coverage: {', '.join(diagnostics['low_vocabulary_coverage_dimensions']) or 'none'}.", "", "### Term assignment frequency", "", "| Term | Subjects | % | Information bits |", "| --- | ---: | ---: | ---: |"]
    for item in diagnostics["terms"]:
        lines.append(f"| `{item['term_id']}` | {item['assigned_subject_count']} | {item['assigned_percent']} | {item['information_bits_when_present'] or '—'} |")
    lines += ["", "## Blind discovery", ""]
    for dimension in review["blind_discovery"]["dimensions"]:
        lines.append(f"### {dimension['dimension']}")
        for concept in dimension["concepts"]:
            lines.append(f"- **{concept['proposed_neutral_concept_label']}** ({concept['approximate_supporting_subject_count']} subjects; {concept['confidence']}): {concept['provisional_definition']}")
        lines.append("")
    lines += ["## Proposals awaiting human decision", ""]
    for priority in ("HIGH", "MEDIUM", "WATCH"):
        selected = [item for item in proposals if item["priority"] == priority]
        lines.append(f"### {priority}")
        if not selected:
            lines.append("- None.")
        for item in selected:
            lines += [f"#### {item['proposal_id']} — {item['operation'].upper()}", "", f"- Affected: {', '.join('`' + value + '`' for value in item['affected_term_ids']) or 'none'}", f"- Proposed: {', '.join('`' + value + '`' for value in item['proposed_term_ids']) or 'none'}", f"- Why: {item['rationale']}", f"- Evidence: {item['evidence_summary']}", f"- Supporting corpus count: {item['supporting_subject_count']}; examples: {', '.join(item['representative_subject_ids']) or 'none'}.", f"- Counterexamples/boundaries: {'; '.join(item['boundary_cases']) or 'none recorded'}", f"- Expected benefit: {item['expected_discovery_value']}", f"- Migration impact: {item['downstream_impact']}", f"- Recommended human decision: {item['recommendation']}"]
            for profile in item["proposed_terms"]:
                lines += [f"- Definition draft `{profile['term_id']}` ({profile['human_label']}): {profile['definition']}", f"  - Include: {profile['inclusion_guidance']}", f"  - Exclude/boundary: {profile['exclusion_boundary_guidance']}"]
            lines.append("")
    audit_counts = Counter(item["disposition"] for item in review["term_audit"])
    lines += ["## Current-term audit", "", "- " + ", ".join(f"{key}: {value}" for key, value in sorted(audit_counts.items())), "", "## ACNC post-hoc comparison", ""]
    for key, values in review["acnc_comparison"].items():
        lines.append(f"### {key.replace('_', ' ').title()}")
        lines.extend(f"- {value}" for value in values) if values else lines.append("- None recorded.")
    lines += ["", "## Run telemetry (private)", "", f"- API calls: {len(telemetry['calls'])}", f"- Tokens: {telemetry['total_input_tokens']} input; {telemetry['total_output_tokens']} output.", f"- Estimated API cost: USD {telemetry['total_estimated_cost_usd']}.", "", "## Human decisions required", "", "For every HIGH proposal: approve, reject, defer/watch, request more evidence, or modify. No proposal is canonical unless separately approved and versioned."]
    return "\n".join(lines) + "\n"

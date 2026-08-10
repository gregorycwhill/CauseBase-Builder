import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from causebase_builder.models import CauseBaseCard, Classification, TaxonomyAmbiguity, TaxonomyMaintenanceSignals, UnmappedConcept
from causebase_builder.openai_client import ApiResult, ApiUsage
from causebase_builder.taxonomy_review import (
    TAXONOMY_REVIEW_VERSION,
    TaxonomyProposal,
    assert_blind_discovery_input,
    build_blind_discovery_input,
    corpus_diagnostics,
    _validate_proposal_semantics,
    run_taxonomy_review,
)


def _taxonomy() -> dict:
    return json.loads(Path("config/taxonomies/causebase-v0.json").read_text(encoding="utf-8"))


def _card(identifier: str, term_id: str | None = None) -> CauseBaseCard:
    classifications = []
    if term_id:
        classifications = [Classification(taxonomy_id="causebase", taxonomy_version="0.1-phase2a", term_id=term_id, term_label=term_id, assignment_method="llm_classification", confidence="medium")]
    return CauseBaseCard(
        causebase_id=identifier, legal_name="Private name", display_name="Private name", entity_status="registered",
        causebase_summary="Restores habitat with local volunteers and runs public working bees for catchment communities.",
        activities=["habitat restoration"], beneficiaries=["catchment communities"], geography=["regional Victoria"], participation_modes=["working bees"],
        classifications=classifications, dataset_version="phase2a-test", built_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
    )


def test_blind_input_excludes_names_acnc_and_current_classifications():
    card = _card("cb_a", "activity.environmental_restoration")
    card.classifications.append(Classification(taxonomy_id="acnc-register", taxonomy_version="2026", term_id="purpose.environment", term_label="Environment", assignment_method="source_native"))
    packet = build_blind_discovery_input([card])

    encoded = json.dumps(packet).lower()
    assert "private name" not in encoded
    assert "classifications" not in encoded
    assert "purpose.environment" not in encoded
    assert_blind_discovery_input(packet)
    with pytest.raises(ValueError, match="forbidden"):
        assert_blind_discovery_input({"records": [{"classifications": []}]})


def test_diagnostics_are_deterministic_and_not_a_taxonomy_mutation():
    taxonomy = _taxonomy()
    before = json.dumps(taxonomy, sort_keys=True)
    cards = [_card("cb_a", "activity.environmental_restoration"), _card("cb_b", "activity.environmental_restoration")]
    first = corpus_diagnostics(cards, taxonomy)
    second = corpus_diagnostics(list(reversed(cards)), taxonomy)

    assert first == second
    assert json.dumps(taxonomy, sort_keys=True) == before
    term = next(item for item in first["terms"] if item["term_id"] == "activity.environmental_restoration")
    assert term["assigned_subject_count"] == 2


def test_future_taxonomy_signals_are_private_and_cannot_be_term_assignments():
    card = _card("cb_a")
    card.taxonomy_maintenance_signals = TaxonomyMaintenanceSignals(
        unmapped_concepts=[UnmappedConcept(dimension="activity", concept_phrase="food rescue", evidence_basis="selected activity text", reason_no_supplied_term_fits="No current activity term")],
        taxonomy_ambiguities=[TaxonomyAmbiguity(dimension="approach", candidate_term_ids=["approach.community_partnership", "approach.volunteer_enabled"], reason="Evidence supports both but boundary is unclear")],
    )
    dumped = card.model_dump(mode="json")
    assert "taxonomy_maintenance_signals" not in dumped
    assert "food rescue" not in json.dumps(dumped)


def test_proposal_validation_rejects_impossible_support_count():
    proposal = TaxonomyProposal(
        proposal_id="TR-001", operation="add", affected_term_ids=[], proposed_term_ids=["activity.example"],
        proposed_terms=[{"term_id": "activity.example", "human_label": "Example", "dimension": "activity", "definition": "Example activity.", "inclusion_guidance": "Include examples.", "exclusion_boundary_guidance": "Exclude other work.", "representative_positive_examples": [], "confusing_neighbour_term_ids": [], "status": "proposed_add"}],
        dimension="activity", rationale="Test", evidence_summary="Test", supporting_subject_count=2,
        representative_subject_ids=["cb_a"], examples=[], boundary_cases=[], expected_discovery_value="Test",
        confidence="medium", priority="MEDIUM", downstream_impact="No automatic change.", recommendation="Human review.",
    )
    with pytest.raises(ValueError, match="more subjects"):
        _validate_proposal_semantics([proposal], [_card("cb_a")])


def _blind_response() -> dict:
    return {"dimensions": [{"dimension": "activity", "concepts": [{"dimension": "activity", "proposed_neutral_concept_label": "Habitat restoration", "provisional_definition": "Hands-on restoration of habitats.", "inclusion_examples": ["restores habitat"], "exclusion_boundary_examples": ["general advocacy"], "approximate_supporting_subject_count": 2, "representative_subject_ids": ["cb_a", "cb_b"], "representative_evidence_phrases": ["restores habitat"], "related_concepts": [], "confidence": "high", "discovery_value": "Distinguishes practical environmental work."}]}], "dimension_gaps": []}


def _critique_response(taxonomy: dict) -> dict:
    return {"proposals": [{"proposal_id": "TR-001", "operation": "refine", "affected_term_ids": ["activity.environmental_restoration"], "proposed_term_ids": ["activity.environmental_restoration"], "proposed_terms": [{"term_id": "activity.environmental_restoration", "human_label": "Environmental restoration", "dimension": "activity", "definition": "Hands-on habitat restoration.", "inclusion_guidance": "Restoring habitat.", "exclusion_boundary_guidance": "Exclude advocacy alone.", "representative_positive_examples": ["restores habitat"], "confusing_neighbour_term_ids": ["activity.advocacy"], "status": "retained_definition_draft", "taxonomy_version": "unapproved"}], "dimension": "activity", "rationale": "Boundary needs explicit guidance.", "evidence_summary": "Two examples show restoration.", "supporting_subject_count": 2, "representative_subject_ids": ["cb_a", "cb_b"], "examples": ["restores habitat"], "boundary_cases": ["advocacy"], "expected_discovery_value": "Clearer filtering.", "confidence": "medium", "priority": "MEDIUM", "downstream_impact": "Two cards may need reclassification review; no automatic change.", "recommendation": "Human review."}], "term_audit": [{"term_id": term["term_id"], "disposition": "retain_with_refinement" if term["term_id"] == "activity.environmental_restoration" else "insufficient_evidence", "rationale": "Fixture review.", "definition_or_boundary_guidance": "Add definitions before a future version."} for term in taxonomy["terms"]], "unchanged_terms": [], "unresolved_questions": ["Need more corpus coverage."]}


def test_review_runs_two_passes_then_posthoc_acnc_comparison(monkeypatch, tmp_path: Path):
    taxonomy = _taxonomy()
    corpus = {"entities": [_card("cb_a", "activity.environmental_restoration").model_dump(mode="json"), _card("cb_b", "activity.environmental_restoration").model_dump(mode="json")]}
    corpus_path, taxonomy_path = tmp_path / "corpus.json", tmp_path / "taxonomy.json"
    corpus_path.write_text(json.dumps(corpus), encoding="utf-8")
    taxonomy_path.write_text(json.dumps(taxonomy), encoding="utf-8")
    payloads = [_blind_response(), _critique_response(taxonomy), {"apparent_overlap": [], "causebase_only_distinctions": ["Participation is separate."], "acnc_categories_causebase_does_not_need": [], "superficially_similar_but_different": [], "accidental_convergence": []}]
    prompts = []

    def fake_call(*, model, input_text, text_format, max_output_tokens, **kwargs):
        prompts.append(input_text)
        return ApiResult(response_id="private", model=model, status="completed", output_text=json.dumps(payloads.pop(0)), usage=ApiUsage(10, 5, 15))

    monkeypatch.setattr("causebase_builder.taxonomy_review.responses_create", fake_call)
    result = run_taxonomy_review(corpus_path=corpus_path, taxonomy_path=taxonomy_path, output_dir=tmp_path / "private-review")

    assert TAXONOMY_REVIEW_VERSION == result["taxonomy_review"]["review_version"]
    assert "activity.environmental_restoration" not in prompts[0]
    assert "baseline_taxonomy" in prompts[1]
    assert "ACNC comparison annex" in prompts[2]
    assert (tmp_path / "private-review" / "taxonomy-review.json").exists()
    assert (tmp_path / "private-review" / "taxonomy-review-private-telemetry.json").exists()
    assert TaxonomyProposal.model_validate(result["taxonomy_review"]["proposals"][0]).operation == "refine"

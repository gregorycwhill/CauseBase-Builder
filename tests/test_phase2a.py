import json
from pathlib import Path

from causebase_builder.phase2a import (
    _cache_path,
    enrich_governed_entity,
    load_governed_entities,
    load_taxonomy,
    make_evidence_pack,
)
from causebase_builder.semantic import semantic_text
from causebase_builder.synthesis import SYNTHESIS_PROMPT_VERSION, synthesis_prompt


def test_cached_phase2a_synthesis_preserves_provenance_and_never_uses_fixture_prior(tmp_path: Path):
    workspace = Path("..").resolve()
    entity = next(
        item for item in load_governed_entities(workspace / "CauseBase-Data" / "governed-inputs" / "reality-spike")
        if item["display_name"] == "Merri Creek Management Committee"
    )
    taxonomy = load_taxonomy(Path("config/taxonomies/causebase-v0.json"))
    pack = make_evidence_pack(entity, workspace / "archive")
    cache_file = _cache_path(tmp_path, pack=pack, taxonomy=taxonomy, model="gpt-5-mini")
    tmp_path.mkdir(exist_ok=True)
    cache_file.write_text(json.dumps({
        "output": {
            "summary": "Manages environmental restoration and community activities in the Merri Creek catchment. The selected evidence records volunteer opportunities, but does not establish the full current program range.",
            "activities": ["environmental restoration", "community activities"],
            "beneficiaries": ["Merri Creek catchment communities"],
            "geography": ["Merri Creek catchment, Victoria"],
            "participation_modes": ["volunteering", "working bees"],
            "taxonomy_term_ids": ["cause.environment", "activity.environmental_restoration", "participation.working_bees"],
            "uncertainty_note": "Selected website evidence is limited to a captured volunteering page."
        },
        "provenance": {
            "model_id": "gpt-5-mini-2025-08-07",
            "prompt_version": "phase2a-0.1",
            "parameters": {"structured_output": True},
            "evidence_input_hash": "a" * 64,
            "generated_at": "2026-08-10T00:00:00+00:00",
            "editorial_policy_version": "0.1",
            "request_id": "resp_test",
            "input_tokens": 100,
            "output_tokens": 50,
            "estimated_cost_usd": "0.000125"
        }
    }), encoding="utf-8")

    card, telemetry = enrich_governed_entity(
        entity=entity,
        archive_root=workspace / "archive",
        cache_root=tmp_path,
        taxonomy=taxonomy,
        dataset_version="phase2a-test",
    )

    assert telemetry["cache_hit"] is True
    assert card.synthesis.model_id == "gpt-5-mini-2025-08-07"
    assert "request_id" not in card.synthesis.model_dump()
    assert "input_tokens" not in card.synthesis.model_dump()
    assert card.fundraising_expenditure is None
    assert any(
        observation.capability == "fundraising_expenditure"
        and observation.status == "not_available_from_source"
        for observation in card.coverage
    )
    assert {item.term_id for item in card.classifications} == {
        "cause.environment", "activity.environmental_restoration", "participation.working_bees"
    }
    assert all(
        not item.evidence_ids for item in card.classifications if item.taxonomy_id == "causebase"
    )
    assert len([item for item in card.coverage if item.capability == "fundraising_expenditure"]) == 1


def test_external_acnc_classifications_are_not_native_inference_or_semantic_input(tmp_path: Path):
    source = {
        "causebase_id": "cb_test", "legal_name": "Example", "display_name": "Example", "entity_status": "registered",
        "coverage": [{"capability": "fundraising_expenditure", "status": "not_yet_processed"}],
        "activities": [], "beneficiaries": [], "participation_modes": [], "financials": {},
        "classifications": [{"taxonomy_id": "acnc-register", "taxonomy_version": "2026", "term_id": "purpose.education", "term_label": "education", "assignment_method": "source_native", "evidence_ids": ["ev:acnc"]}],
        "evidence": [{"evidence_id": "ev:acnc", "source_type": "regulatory", "title": "ACNC", "observed_at": "2026-08-10"}],
    }
    pack = make_evidence_pack(source, Path("..") / "archive")
    assert "purpose.education" not in str(pack)
    from causebase_builder.pipeline import build_card
    card = build_card(source, "test")
    assert "purpose.education" not in semantic_text(card)


def test_current_synthesis_prompt_requests_dense_summaries_only_when_evidence_supports_them():
    prompt = synthesis_prompt(evidence_pack={"selected_private_excerpts": []}, taxonomy_terms=[])

    assert SYNTHESIS_PROMPT_VERSION == "phase2a-0.5"
    assert "150–220 word summary" in prompt
    assert "genuinely sparse" in prompt
    assert "Do not say that ACNC does not list purposes" in prompt

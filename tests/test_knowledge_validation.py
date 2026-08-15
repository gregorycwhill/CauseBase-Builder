import json
from pathlib import Path

import pytest

from causebase_builder.knowledge_validation import ReviewDecision, automation_policy, prepare, score_decisions, select_review_sample


def _input(tmp_path: Path):
    candidates = []
    for index, domain in enumerate(("activities", "beneficiaries", "geography", "programs", "participation") * 3):
        candidates.append({"domain": domain, "source_text": f"We do useful work for people {index}", "source_location": "p", "source_url": "https://example.org", "page_role": "homepage", "stable_class": "stable", "claim_basis": "direct_source_text", "extraction_method": "deterministic_html_parser_v2"})
    pilot = {"web": [{"case_id": "case-a", "candidates": candidates}, {"case_id": "case-b", "candidates": candidates[:4]}]}
    golden = {"cases": [{"case_id": "case-a", "causebase_id": "cb_a"}, {"case_id": "case-b", "causebase_id": "cb_b"}]}
    pp, gp = tmp_path / "pilot.json", tmp_path / "golden.json"; pp.write_text(json.dumps(pilot)); gp.write_text(json.dumps(golden)); return pp, gp


def test_prepare_is_deterministic_review_only_and_preserves_provenance(tmp_path: Path):
    pilot, golden = _input(tmp_path)
    first = prepare(pilot_path=pilot, golden_path=golden, output_dir=tmp_path / "one", target=12)
    second = prepare(pilot_path=pilot, golden_path=golden, output_dir=tmp_path / "two", target=12)
    assert first["inventory"] == second["inventory"]
    assert first["review_sample"] == second["review_sample"]
    assert len(first["review_sample"]) == 12
    assert {item["causebase_id"] for item in first["review_sample"]} == {"cb_a", "cb_b"}
    assert all(item["source_excerpt"] and item["source_evidence_hash"] for item in first["review_sample"])
    assert (tmp_path / "one" / "semantic-review-decisions.json").read_text().strip() == "[]"


def test_review_decision_is_human_only_and_requires_valid_vocabulary():
    assert ReviewDecision(case_id="kv1-x", outcome="REJECT", rationale="Boilerplate").decision_authority == "human_governed"
    with pytest.raises(Exception): ReviewDecision(case_id="kv1-x", outcome="MODEL_ACCEPT")


def test_pre_human_policy_is_not_ready_and_never_auto_promotes():
    policy = automation_policy([])
    assert policy["activities"]["policy"] == "NOT READY"
    assert policy["fundraising"]["policy"] == "NOT READY"


def test_domain_scoring_resolves_human_decision_against_review_case(tmp_path: Path):
    pilot, golden = _input(tmp_path)
    result = prepare(pilot_path=pilot, golden_path=golden, output_dir=tmp_path / "out", target=8)
    decision = ReviewDecision(case_id=result["review_sample"][0]["case_id"], outcome="ACCEPT")
    policy = score_decisions(result["review_sample"], [decision])
    assert sum(item["reviewed"] for item in policy.values()) == 1
    with pytest.raises(ValueError, match="unknown"):
        score_decisions(result["review_sample"], [ReviewDecision(case_id="kv1-missing", outcome="REJECT")])


def test_selection_rejects_unbounded_sample():
    with pytest.raises(ValueError): select_review_sample([], target=61)

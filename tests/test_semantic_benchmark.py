import json
from pathlib import Path

import pytest

from causebase_builder.knowledge_validation import automation_policy
from causebase_builder.semantic_benchmark import (
    BenchmarkReviewDecision,
    FIAAwardsAdapter,
    PFRAAdapter,
    build_cohort,
    conservative_identity_candidates,
    assessment_scopes,
    DonorRepublicFunraisinAdapter,
    FIAAwardsAdapter,
    PFRAAdapter,
    emit_domain_candidates,
    prepare_benchmark,
)


def test_candidate_ids_are_deterministic_and_non_exclusive():
    passages = [{"text": "Our fundraising campaign supports families", "location": "p:1"}]
    candidates = emit_domain_candidates(
        subject_id="cb:1", source_url="https://example.org", source_family="website",
        source_role="organisation_self_report", source_record_id="src:1", passages=passages,
        domain_markers={"fundraising_campaign": ("campaign",), "beneficiaries": ("families",)},
    )
    assert len(candidates) == 2
    assert [item.candidate_id for item in candidates] == [item.candidate_id for item in emit_domain_candidates(
        subject_id="cb:1", source_url="https://example.org", source_family="website",
        source_role="organisation_self_report", source_record_id="src:1", passages=passages,
        domain_markers={"fundraising_campaign": ("campaign",), "beneficiaries": ("families",)},
    )]
    assert all(item.review_status == "review_required" and item.pipeline_stage == "P1" for item in candidates)


def test_benchmark_review_separates_semantics_and_blockers():
    decision = BenchmarkReviewDecision(
        case_id="seb1-x", semantic_outcome="EDIT", blockers=["IDENTITY_BLOCKED"], rationale="Evidence is usable after editing; identity remains unresolved."
    )
    assert decision.decision_authority == "human_governed"
    with pytest.raises(ValueError):
        BenchmarkReviewDecision(case_id="seb1-y", semantic_outcome="EDIT")


def test_identity_binding_is_exact_only():
    resolved = conservative_identity_candidates(source_record_id="src:1", external_identifier="abn:1", known_identifiers={"abn:1": "cb:1"})
    unresolved = conservative_identity_candidates(source_record_id="src:2", external_identifier=None, known_identifiers={"abn:1": "cb:1"})
    assert resolved.status == "resolved" and resolved.candidate_subject_id == "cb:1"
    assert unresolved.status == "unresolved" and unresolved.candidate_subject_id is None


def test_assessment_scope_does_not_claim_unprocessed_sources():
    assert assessment_scopes([]) == []
    assert assessment_scopes([], [{"subject_id": "cb:1", "domain": "fundraising_campaign", "source_families": [], "source_roles": []}]) == []
    rows = assessment_scopes([], [{"subject_id": "cb:1", "domain": "fundraising_campaign", "source_families": ["fundraising_industry_benchmark"], "source_roles": ["fundraising_industry_benchmark"]}])
    assert rows[0].source_families == ["fundraising_industry_benchmark"]


def test_donor_benchmark_role_and_caveat_are_source_specific():
    adapter = DonorRepublicFunraisinAdapter()
    assert adapter.source_role == "fundraising_industry_benchmark"
    records = adapter.enumerate_records("Top 30 campaign raised $1,000,000")
    assert records[0]["caveat"].startswith("Public revenue may omit offline funds")
    assert records[0]["reported_amount_2023"] is not None


def test_fia_and_pfra_source_parsers_retain_native_relationship_fields():
    fia = FIAAwardsAdapter().enumerate_records("Winner: Charity — Campaign nominated by Agency")
    assert fia[0]["status"] == "winner" and fia[0]["nominated_by"] == "Agency"
    pfra = PFRAAdapter().enumerate_records("RFDS Victoria partnership with Cornucopia Consultancy")
    assert pfra[0]["source_text"]


def test_pfra_html_preserves_external_linked_domain():
    records = PFRAAdapter().enumerate_html('<a href="https://charity.example.org">Example Charity</a>')
    assert records[0]["linked_domain"] == "charity.example.org"


def test_top30_rows_are_logical_and_bounded():
    rows = DonorRepublicFunraisinAdapter().enumerate_top30_rows("\n".join(f"Campaign {i} raised ${i},000" for i in range(40)))
    assert len(rows) == 30
    assert all(row["record_type"] == "top30_campaign" for row in rows)


def test_cohort_is_bounded_and_deterministic():
    rows = [{"subject_id": f"cb:{index}", "size": "small"} for index in range(45)]
    first = build_cohort(rows)
    second = build_cohort(rows)
    assert len(first.subjects) == 40
    assert first.model_dump() == second.model_dump()


def test_prepare_is_private_deterministic_and_model_free(tmp_path: Path):
    summary = prepare_benchmark(
        subjects=[{"subject_id": "cb:1"}, {"subject_id": "cb:2"}],
        output_dir=tmp_path,
        adapter_text={"pfra": "Face-to-face fundraising agency", "fia_awards": "Campaign award"},
        target=2,
    )
    assert summary["review_only"] is True
    assert summary["model_calls"] == {"P2": 0, "P3": 0, "O": 0}
    assert summary["adapter_results"][0]["status"] == "enumerated"
    assert summary["adapter_results"][1]["status"] == "not_acquired"
    assert (tmp_path / "candidate-inventory.jsonl").exists()
    assert not (tmp_path / "review-decisions.json").exists()


def test_industry_adapters_preserve_source_metric_wording():
    text = "Campaign raised $10,000; provider agency listed."
    records = PFRAAdapter().enumerate_records(text)
    assert records and records[0]["metric_wording_preserved"] is True
    assert FIAAwardsAdapter().candidates("campaign award provider")


def test_reviewed_policy_explanation_acknowledges_human_evidence():
    policy = automation_policy([])
    assert "No human-adjudicated evidence" in policy["fundraising"]["reason"]

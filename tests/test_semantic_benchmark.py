import json
from pathlib import Path

import pytest

from causebase_builder.knowledge_validation import automation_policy
from causebase_builder.semantic_benchmark import (
    BenchmarkReviewDecision,
    FIAAwardsAdapter,
    PFRAAdapter,
    normalize_v05_population,
    normalize_host,
    selection_matrix,
    build_acnc_backbone_index,
    crosswalk_against_acnc,
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


def test_pfra_directory_member_cards_deduplicate_and_preserve_roles():
    html = '<h4>Charity One</h4><a href="https://one.example/">https://one.example/</a><h4>Charity One</h4><a href="https://one.example/">https://one.example/</a>'
    records = PFRAAdapter().enumerate_html(html, directory_role="current_charity_membership")
    assert len(records) == 1 and records[0]["record_type"] == "current_charity_membership" and records[0]["charity_label"] == "Charity One"


def test_acnc_backbone_crosswalk_keeps_name_review_only():
    index = build_acnc_backbone_index([{"source_record_id": "acnc:1", "source_fields": {"ABN": "123", "Legal Name": "Example Charity", "Website": "www.example.org"}}])
    rows = crosswalk_against_acnc([{"source_record_id": "x", "charity_label": "Example Charity"}], index)
    assert rows[0]["acnc_identity"]["status"] == "candidate"


def test_top30_rows_are_logical_and_bounded():
    rows = DonorRepublicFunraisinAdapter().enumerate_top30_rows("1 | Harbour Walk | Example Charity | walk | $10,000 | $12,000 | +20%\n2 | Cycle Challenge | Other Charity | cycling | $20,000 | $21,000 | +5%")
    assert len(rows) == 2
    assert rows[0]["charity_source_organisation_label"] == "Example Charity"
    assert rows[0]["activity_mechanic"] == "walk"
    assert rows[0]["reported_amount_2023"] and rows[0]["reported_amount_2024"]
    assert all(row["record_type"] == "top30_campaign" for row in rows)


def test_nested_v05_population_normalizer_and_host():
    rows = normalize_v05_population({"entities": [{"causebase_id": "cb:1", "identity": {"display_name": "Example", "legal_name": "Example Ltd", "operating_names": ["Ex"], "website": "HTTPS://WWW.Example.org/path", "external_identifiers": [{"scheme": "abn", "value": "1"}]}, "subject_kind": "organisation", "evidence": [{}], "financial_records": [{}]}]})
    assert rows[0]["website_domain"] == "example.org"
    assert rows[0]["external_identifiers"][0]["value"] == "1"
    assert normalize_host("https://WWW.Example.org/a") == "example.org"


def test_selection_matrix_counts_exact_and_candidate_hits():
    population = [{"subject_id": "cb:1", "display_name": "Example", "website_domain": "example.org"}]
    crosswalk = [{"source_family": "fundraising_industry_pfra", "identity_binding": {"status": "resolved", "subject_id": "cb:1"}}, {"source_family": "fundraising_industry_awards", "organisation": "Example", "identity_binding": {"status": "candidate", "subject_id": None}}]
    row = selection_matrix(population, crosswalk)[0]
    assert row["fundraising_industry_hit_count"] == 2 and row["exact_industry_hit"] and row["candidate_industry_hit"]


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

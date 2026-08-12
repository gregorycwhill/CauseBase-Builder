from datetime import date

from causebase_builder.change_detection import build_change_profile, refresh_targets
from causebase_builder.models import SubjectRelationship


def test_financial_only_change_reuses_semantic_derivatives():
    profile = build_change_profile(
        {"financial_records": [{"revenue": "100"}], "activities": ["food relief"]},
        {"financial_records": [{"revenue": "110"}], "activities": ["food relief"]},
    )
    assert profile.changed_dimensions == ("financial",)
    decisions = refresh_targets(profile)
    assert decisions["summary"] == "reuse"
    assert decisions["embedding"] == "reuse"


def test_new_program_refreshes_semantic_derivatives():
    profile = build_change_profile({"activities": ["food relief"]}, {"activities": ["food relief", "legal clinic"]})
    decisions = refresh_targets(profile)
    assert decisions["summary"] == "refresh"
    assert decisions["taxonomy"] == "refresh"
    assert decisions["embedding"] == "refresh"


def test_temporal_relationship_preserves_validity_without_identity_replacement():
    relationship = SubjectRelationship(
        relationship_type="part_of", target_causebase_id="cb_national", valid_from=date(2019, 1, 1),
        valid_to=date(2026, 1, 1), observed_at=date(2026, 8, 12), status="ended",
    )
    assert relationship.target_causebase_id == "cb_national"
    assert relationship.valid_from < relationship.valid_to

import pytest

from charitygraph.registry import SubjectRegistry


def _mint(registry, name="Example"):
    return registry.mint(display_name=name, subject_kind="organisation", resolution_status="resolved", resolution_basis="ABN match", source_record_ids=["src:test"])


def test_only_resolved_subjects_mint_opaque_stable_ids(tmp_path):
    registry = SubjectRegistry.load(tmp_path / "registry.json")
    subject = _mint(registry)
    registry.save()
    assert subject["causebase_id"].startswith("cb_")
    assert "Example" not in subject["causebase_id"]
    assert SubjectRegistry.load(tmp_path / "registry.json").get(subject["causebase_id"])["causebase_id"] == subject["causebase_id"]
    with pytest.raises(ValueError, match="resolved"):
        registry.mint(display_name="No", subject_kind="organisation", resolution_status="ambiguous", resolution_basis="name", source_record_ids=[])


def test_merge_and_split_keep_old_ids_resolvable(tmp_path):
    registry = SubjectRegistry.load(tmp_path / "registry.json")
    survivor, loser = _mint(registry, "A"), _mint(registry, "B")
    registry.merge(survivor_id=survivor["causebase_id"], loser_id=loser["causebase_id"])
    assert registry.get(loser["causebase_id"])["successor_ids"] == [survivor["causebase_id"]]
    successors = registry.split(
        original_id=survivor["causebase_id"],
        successors=[
            {"display_name": "A1", "subject_kind": "organisation", "resolution_status": "resolved", "resolution_basis": "review", "source_record_ids": ["src:a1"]},
            {"display_name": "A2", "subject_kind": "organisation", "resolution_status": "resolved", "resolution_basis": "review", "source_record_ids": ["src:a2"]},
        ],
    )
    assert registry.get(survivor["causebase_id"])["identity_lifecycle_status"] == "split"
    assert all(registry.get(item["causebase_id"])["predecessor_ids"] == [survivor["causebase_id"]] for item in successors)


def test_card_binding_requires_current_registered_identity(tmp_path):
    registry = SubjectRegistry.load(tmp_path / "registry.json")
    subject = _mint(registry)

    class Card:
        causebase_id = subject["causebase_id"]

    assert registry.validate_card_bindings([Card()]) == []
    registry.get(subject["causebase_id"])["identity_lifecycle_status"] = "void"
    assert "cannot publish active card" in registry.validate_card_bindings([Card()])[0]


def test_authoritative_acnc_promotion_mints_unknown_subject_and_never_duplicates_source(tmp_path):
    registry = SubjectRegistry.load(tmp_path / "registry.json")
    subject = registry.promote_authoritative_acnc(
        source_record_id="src:acnc-register:example", abn="51 214 424 410",
        legal_name="Example Federated Branch Incorporated",
        source_id="acnc-registered-charities-2026-08-10", source_version="2026-08-10",
        evidence_ids=["ev:acnc:example"],
    )
    assert subject["subject_kind"] == "unknown"
    assert subject["promotion"]["promotion_method"] == "automated_authoritative_source"
    assert subject["promotion"]["promotion_policy"] == "acnc-authoritative-v1"
    assert subject["promotion"]["external_identifiers"]["abn"] == ["51214424410"]
    with pytest.raises(ValueError, match="already governedly bound"):
        registry.promote_authoritative_acnc(
            source_record_id="src:acnc-register:example", abn="51214424410",
            legal_name="Example Federated Branch Incorporated",
            source_id="acnc-registered-charities-2026-08-10", source_version="2026-08-10",
            evidence_ids=["ev:acnc:example"],
        )

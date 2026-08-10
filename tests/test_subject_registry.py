import pytest

from causebase_builder.registry import SubjectRegistry


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

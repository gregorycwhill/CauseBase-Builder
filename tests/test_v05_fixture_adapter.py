import json
from pathlib import Path
from copy import deepcopy
from causebase_builder.v05 import ReleaseContext, adapt_rc4_card, adapt_rc4_fixture, validate_v05_card
from causebase_builder.v05.models import CapabilityRegistry
from causebase_builder.v05.stage import stage_rc4_release

DATA=Path(__file__).parents[2]/"CauseBase-Data"/"examples"/"vnext"
def load(name): return json.loads((DATA/name).read_text(encoding="utf-8"))
def registry(): return CapabilityRegistry.model_validate(load("capability-registry.json"))
def ids(card): return set(card["source_record_refs"])
def test_eja_adapter_losslessly_reconstructs_frozen_statements():
    expected=load("eja.json"); source=load("eja-rc4-source-fixture.json")
    context=ReleaseContext(release_id=expected["release"]["release_id"],dataset_version=expected["release"]["dataset_version"],based_on_release=expected["release"]["based_on_release"],generated_at=expected["release"]["generated_at"],capability_registry={"registry_id":"capability-registry-0.5-initial","path":"examples/vnext/capability-registry.json"})
    actual=adapt_rc4_fixture(source,expected,context)
    assert actual["financial_reports"][0]["statements"] == expected["financial_reports"][0]["statements"]
    assert not validate_v05_card(actual,registry(),ids(actual))
def test_four_fixtures_have_complete_registry_coverage():
    for name in ["eja.json","sparse.json","identity-case.json","multiple-financial-periods.json"]:
        card=load(name); assert not validate_v05_card(card,registry(),ids(card))
def test_adapter_accepts_all_four_immutable_rc4_cards_without_subject_branches():
    pairs=[("eja.json","cb_604da7f26c6c48dd934e713edc493e9f"),("sparse.json","cb_5d5459e58dac4e49a042f717e395ebec"),("identity-case.json","cb_408c113ff48c4b4f91c7697b00b211dd"),("multiple-financial-periods.json","cb_4434434d6c6e425faf0dd56cb29ef8bf")]
    rc4_dir=DATA.parents[1]/"releases"/"rc4-2026-08-14"/"cards"
    for fixture, subject_id in pairs:
        expected=load(fixture); rc4=json.loads((rc4_dir/f"{subject_id}.json").read_text(encoding="utf-8"))
        context=ReleaseContext(release_id=expected["release"]["release_id"],dataset_version=expected["release"]["dataset_version"],based_on_release=expected["release"]["based_on_release"],generated_at=expected["release"]["generated_at"],capability_registry={"registry_id":"capability-registry-0.5-initial","path":"examples/vnext/capability-registry.json"})
        actual=adapt_rc4_fixture(rc4,expected,context)
        assert actual["causebase_id"] == subject_id
        assert not validate_v05_card(actual,registry(),ids(actual))
def test_v05_negative_contract_guards():
    card=load("eja.json")
    broken=deepcopy(card); broken["coverage"]["current"].pop(); assert any("coverage" in x for x in validate_v05_card(broken,registry(),ids(broken)))
    broken=deepcopy(card); broken["canonical_metrics"][0]["observation_id"]="missing"; assert any("canonical" in x for x in validate_v05_card(broken,registry(),ids(broken)))
    broken=deepcopy(card); broken["source_statement_fixture"]="private"; assert validate_v05_card(broken,registry(),ids(broken))
    broken=deepcopy(card); broken["analytic_projections"][0]["amount"]={"source_amount":"1"}; assert any("source_amount" in x for x in validate_v05_card(broken,registry(),ids(broken)))
    broken=deepcopy(card); broken["analytic_projections"][0].pop("derivation"); assert any("derivation" in x for x in validate_v05_card(broken,registry(),ids(broken)))
    broken=deepcopy(card); broken["derivatives"][0]["generated_under"]["output_contract_version"]="0.5"; assert any("derivative" in x for x in validate_v05_card(broken,registry(),ids(broken)))
    dfwa=load("identity-case.json"); assert dfwa["relationships"]==[] and dfwa["identity_resolution_notice"]["status"]=="unresolved_structure"
def test_production_adapter_never_accepts_expected_card_or_invents_provenance():
    source=json.loads((DATA.parents[1]/"releases"/"rc4-2026-08-14"/"cards"/"cb_604da7f26c6c48dd934e713edc493e9f.json").read_text(encoding="utf-8"))
    context=ReleaseContext(release_id="v05-test",dataset_version="v05-test",based_on_release="phase2b-2026-08-14-rc4-fundraising-projection-correction",generated_at="2026-08-15T00:00:00Z",capability_registry={"registry_id":"capability-registry-0.5-initial","path":"x"})
    sidecars={}
    for path in (DATA.parents[1]/"releases"/"rc4-2026-08-14"/"source-records").glob("*.json"):
        item=json.loads(path.read_text(encoding="utf-8")); sidecars[item["source_record_id"]]=item
    card=adapt_rc4_card(source,sidecars,registry(),context)
    assert card["legacy_unbound"]["activities"] == source["activity_observations"]
    adapter=(Path(__file__).parents[1]/"src"/"causebase_builder"/"v05"/"adapter.py").read_text(encoding="utf-8")
    assert "examples/vnext" not in adapter and "causebase_id ==" not in adapter

def test_full_rc4_staging_migrates_all_cards_to_temp_directory(tmp_path):
    context=ReleaseContext(release_id="v05-test",dataset_version="v05-test",based_on_release="phase2b-2026-08-14-rc4-fundraising-projection-correction",generated_at="2026-08-15T00:00:00Z",capability_registry={"registry_id":"capability-registry-0.5-initial","path":"x"})
    cards=stage_rc4_release(DATA.parents[1]/"releases"/"rc4-2026-08-14",tmp_path,registry(),context)
    assert len(cards)==120 and len(list((tmp_path/"cards").glob("*.json")))==120

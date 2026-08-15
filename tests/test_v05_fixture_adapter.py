import json
from pathlib import Path
from copy import deepcopy
from causebase_builder.v05 import ReleaseContext, adapt_rc4_fixture, validate_v05_card
from causebase_builder.v05.models import CapabilityRegistry

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
def test_v05_negative_contract_guards():
    card=load("eja.json")
    broken=deepcopy(card); broken["coverage"]["current"].pop(); assert any("coverage" in x for x in validate_v05_card(broken,registry(),ids(broken)))
    broken=deepcopy(card); broken["canonical_metrics"][0]["observation_id"]="missing"; assert any("canonical" in x for x in validate_v05_card(broken,registry(),ids(broken)))
    broken=deepcopy(card); broken["source_statement_fixture"]="private"; assert validate_v05_card(broken,registry(),ids(broken))
    broken=deepcopy(card); broken["analytic_projections"][0]["amount"]={"source_amount":"1"}; assert any("source_amount" in x for x in validate_v05_card(broken,registry(),ids(broken)))
    broken=deepcopy(card); broken["analytic_projections"][0].pop("derivation"); assert any("derivation" in x for x in validate_v05_card(broken,registry(),ids(broken)))
    broken=deepcopy(card); broken["derivatives"][0]["generated_under"]["output_contract_version"]="0.5"; assert any("derivative" in x for x in validate_v05_card(broken,registry(),ids(broken)))
    dfwa=load("identity-case.json"); assert dfwa["relationships"]==[] and dfwa["identity_resolution_notice"]["status"]=="unresolved_structure"

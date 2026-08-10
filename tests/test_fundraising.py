import json
from pathlib import Path

from causebase_builder.fundraising import estimate_fundraising


FIXTURE = Path("tests/fixtures/source/entities.json")


def entities():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["entities"]


def test_direct_fundraising_estimate():
    estimate = estimate_fundraising(entities()[0])
    assert estimate.normalised_amount == 12000
    assert estimate.method == "direct_extract"
    assert estimate.confidence == "high"


def test_heuristic_fundraising_estimate_excludes_unrelated_cost():
    estimate = estimate_fundraising(entities()[1])
    assert estimate.normalised_amount == 87000
    assert estimate.method == "heuristic_estimate"
    assert {c.label for c in estimate.components} == {"Marketing", "Public relations"}
    assert estimate.rule_id == "CB-FUND-H03"


def test_fallback_prior_is_never_blank():
    estimate = estimate_fundraising(entities()[2])
    assert estimate.normalised_amount == 43500
    assert estimate.method == "fallback_prior"
    assert estimate.confidence == "low"
    assert estimate.plausible_low < estimate.normalised_amount < estimate.plausible_high

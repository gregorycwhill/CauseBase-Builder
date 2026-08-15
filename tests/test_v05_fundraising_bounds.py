import pytest
from causebase_builder.v05.fundraising import AttributionComponent, calculate_bounds

def component(identifier, amount, treatment, basis):
    return AttributionComponent(observation_id=identifier,amount={"amount":amount,"currency":"AUD"},treatment=treatment,additivity_basis=basis)
def test_bounds_are_additive_and_do_not_invent_a_midpoint():
    result=calculate_bounds([component("a","100","definite","row-a"),component("b","50","possible","row-b"),component("c","10","excluded","row-c")])
    assert result.lower_bound.amount=="100" and result.upper_bound.amount=="150" and result.point_estimate is None
def test_bounds_reject_overlap_and_invalid_order():
    with pytest.raises(ValueError,match="additivity"): calculate_bounds([component("a","100","definite","same"),component("b","50","possible","same")])
    with pytest.raises(ValueError,match="upper bound"): __import__('causebase_builder.v05.fundraising',fromlist=['FundraisingBounds']).FundraisingBounds(lower_bound={"amount":"2","currency":"AUD"},upper_bound={"amount":"1","currency":"AUD"})

from charitygraph.evidence_engine import _identity, _fundraising

def test_identity_pilot_does_not_mint_from_name_or_website():
    result=_identity({"case_id":"ambiguous","strata":["identity_ambiguity"]},{"causebase_id":"cb_x","identity":{"website":"example.org"}})
    assert result["status"]=="review_required" and result["minted_subject"] is False
    assert _identity({"case_id":"unbound","strata":[]},None)["status"]=="unresolved"

def test_fundraising_pilot_retains_additivity_block():
    assert _fundraising({"case_id":"x","strata":["fundraising_overlap"]})["status"]=="additivity_blocked"

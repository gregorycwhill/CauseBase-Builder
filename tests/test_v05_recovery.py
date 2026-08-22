from charitygraph.v05.recovery import legacy_unbound, recover_exact

def test_exact_recovery_never_uses_fuzzy_values():
    records=[{"source_record_id":"src:test","source_fields":{"Beneficiaries":["Children"]}}]
    assert recover_exact("Children",records)=={"source_record_id":"src:test","source_location":"/source_fields/Beneficiaries/0","recovery_rule":"exact_public_value_match"}
    assert recover_exact("children",records) is None
def test_legacy_unbound_preserves_exact_payload_with_rc4_hash():
    card={"causebase_id":"cb_test"}; value=legacy_unbound("rc4",card,{"activities":[{"value":"Legacy"}],"beneficiaries":[]})
    assert value["origin_release"]=="rc4" and len(value["origin_card_sha256"])==64 and value["activities"][0]["value"]=="Legacy"

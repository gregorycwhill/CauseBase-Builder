from causebase_builder.document_v2.evaluate import _compute_decision


def test_document_decision_is_derived_from_hard_gates():
    financial={"profit_and_loss":{"passed":True},"financial_position":{"passed":True}}
    decision, reasons=_compute_decision(financial,{"passed":True},{"passed":True},[{"status":"completed"}])
    assert decision=="decisive" and not reasons
    decision, reasons=_compute_decision(financial,{"passed":True},{"passed":False},[{"status":"completed"}])
    assert decision=="conditional" and "visual" in reasons[0]
    decision, _=_compute_decision({"profit_and_loss":{"passed":False},"financial_position":{"passed":True}},{"passed":True},{"passed":True},[{"status":"completed"}])
    assert decision=="failed"

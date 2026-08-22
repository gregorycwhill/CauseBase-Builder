"""Independent structural/reference validators for public contract 0.5."""
from __future__ import annotations
from .models import Card, CapabilityRegistry

FORBIDDEN = ("archive", "prompt", "token", "estimated_cost", "fixture")
def validate_v05_card(raw: dict, registry: CapabilityRegistry, source_record_ids: set[str]) -> list[str]:
    errors=[]
    try: card=Card.model_validate(raw)
    except Exception as exc: return [str(exc)]
    if any(key in raw for key in ("source_statement_fixture",)): errors.append("fixture-only field in public card")
    evidence={x.evidence_id for x in card.evidence}; observations={}
    for name in ("activities","beneficiaries","descriptive_geography","funding_sources","fundraising_methods","participation","opportunities","programs","relationships","classifications","analytic_projections"):
        for item in getattr(card,name):
            if item.get("observation_id") in observations: errors.append("duplicate observation ID")
            if item.get("observation_id"): observations[item["observation_id"]]=item
            if not set(item.get("evidence_ids",[])) <= evidence: errors.append("broken evidence reference")
    for report in card.financial_reports:
        if report["source_record_id"] not in source_record_ids: errors.append("broken source-record reference")
        for observation in report.get("structured_observations",[]): observations[observation["observation_id"]]=observation
        for statement in report.get("statements",[]):
            for row in statement.get("rows",[]): observations[row["observation_id"]]=row
    for metric in card.canonical_metrics:
        if metric["observation_id"] not in observations: errors.append("broken canonical financial pointer")
    for projection in card.analytic_projections:
        if projection.get("claim_basis") != "direct" and not projection.get("derivation"): errors.append("non-direct claim without derivation")
        if "amount" in projection and isinstance(projection["amount"], dict) and "source_amount" in projection["amount"]: errors.append("derived amount uses source_amount")
        for key in ("component_observation_ids",):
            if not set(projection.get(key, [])) <= set(observations): errors.append("broken analytic component pointer")
        if projection.get("denominator_observation_id") and projection["denominator_observation_id"] not in observations: errors.append("broken analytic denominator pointer")
    for item in card.participation:
        if item.get("action_url") and item.get("action_url") in {x.url for x in card.evidence}: errors.append("participation evidence URL used as action URL")
    for derivative in card.derivatives:
        if derivative.get("generated_under", {}).get("output_contract_version") == "0.5" and derivative.get("current_assessment", {}).get("disposition") == "reused": errors.append("historical derivative contract rewritten")
    actual=[x["capability"] for x in card.coverage["current"]]; expected=[x.capability_id for x in registry.capabilities]
    if card.coverage["registry_id"] != registry.registry_id or len(actual)!=len(set(actual)) or set(actual)!=set(expected): errors.append("incomplete or duplicate coverage")
    if any(any(part in str(value).lower() for part in FORBIDDEN) for value in raw.values() if isinstance(value,str)): errors.append("private/public boundary leak")
    return errors
def validate_v05_fixture_release(cards: list[dict], registry: CapabilityRegistry, source_record_ids: set[str]) -> list[str]:
    return [f"{card.get('causebase_id')}: {error}" for card in cards for error in validate_v05_card(card,registry,source_record_ids)]

"""Deterministic RC4-to-0.5 fixture adapter; no I/O, fetching, or model calls."""
from __future__ import annotations
from copy import deepcopy
from .models import ReleaseContext, CapabilityRegistry
from .recovery import legacy_unbound, recover_exact

class MigrationBlocker(ValueError):
    """Raised when immutable RC4 data cannot be represented without guessing."""

def _sign(money: dict | None) -> str:
    if money is None: return "not_applicable"
    value = money["source_amount"]
    return "negative" if value.startswith("-") else "zero" if value == "0" else "positive"

def _row(row: dict, causebase_id: str, source_record_id: str, period: dict) -> dict:
    return {"observation_id": row["observation_id"], "subject_id": causebase_id, "kind": "financial_statement_row", "claim_basis": "direct", "extraction_method": "table", "source_record_ids": [source_record_id], "evidence_ids": row["evidence_ids"], "time": {"reporting_period": period}, "confidence": row.get("extraction_confidence"), "warnings": row.get("extraction_warnings", []), "source_label": row["source_label"], "row_type": row["row_type"], "source_order": row["source_order"], "hierarchy_indent": row.get("hierarchy_indent"), "amount": row.get("current_amount"), "comparatives": [{"period": {"label": item.get("label")}, "amount": item["amount"]} for item in row.get("comparative_periods", [])], "source_location": row.get("source_location"), "source_sign": _sign(row.get("current_amount"))}

def _financial_reports(card: dict, source_records: dict[str,dict]) -> tuple[list[dict], list[dict], list[dict]]:
    reports=[]
    metrics=[]
    unbound=[]
    for financial in card.get("financial_records",[]):
        evidence_ids=financial.get("evidence_ids",[])
        source_id=next((key for key,record in source_records.items() if set(evidence_ids)&set(record.get("evidence_ids",[]))),None)
        if not source_id:
            unbound.append(financial)
            continue
        original_period=financial.get("period",{}); label=original_period.get("label")
        period={"start":original_period.get("period_start"),"end":original_period.get("period_end"),"label":label}
        period={key:value for key,value in period.items() if value is not None}
        statements=[]
        for source in financial.get("statements",[]):
            statements.append({"statement_id":f"stmt:{financial['financial_record_id']}:{source['statement_type']}","statement_type":source["statement_type"],"printed_title":source["statement_title"],"reporting_period":{"label":label},"reporting_scope":source.get("reporting_scope","unknown"),"currency":source.get("currency"),"source_location":None,"rows":[_row(row,card["causebase_id"],source_id,{"label":label}) for row in source.get("rows",[])]})
        allocations=[]
        for ordinal,item in enumerate(financial.get("functional_expense_allocations",[])):
            allocation={"observation_id":f"obs:{financial['financial_record_id']}:allocation:{ordinal}","subject_id":card["causebase_id"],"kind":"functional_expense_allocation","claim_basis":"direct","extraction_method":"vision","source_record_ids":[source_id],"evidence_ids":item.get("evidence_ids",[]),"time":{"reporting_period":{"label":label}},"warnings":[item["derivation_note"]] if item.get("derivation_note") else [],"allocation_label":item["source_label"],"share":item["share"],"share_precision":"rounded whole percent"}
            allocations.append(allocation)
        structured=[]
        metric_aliases={"revenue":"revenue","total_expenses":"total_expenses","assets":"total_assets","liabilities":"total_liabilities","net_assets":"net_assets_equity"}
        for name in ("revenue","donations","government_grants","employee_costs","total_expenses","assets","liabilities","net_assets"):
            amount=financial.get(name)
            if amount is None: continue
            observation_id=f"obs:{financial['financial_record_id']}:{name}"
            structured.append({"observation_id":observation_id,"subject_id":card["causebase_id"],"kind":"structured_financial_observation","claim_basis":"direct","extraction_method":"api","source_record_ids":[source_id],"evidence_ids":evidence_ids,"time":{"reporting_period":period},"warnings":[],"metric":name,"amount":amount})
            if name in metric_aliases:
                metrics.append({"metric_id":f"metric:{financial['financial_record_id']}:{name}","metric":metric_aliases[name],"observation_id":observation_id,"sign_normalisation":"as_reported","reconciliation_status":"single_observation"})
        consolidated=financial.get("consolidated")
        reports.append({"financial_report_id":financial["financial_record_id"],"source_record_id":source_id,"evidence_ids":evidence_ids,"reporting_period":period,"reporting_scope":financial.get("reporting_scope","unknown"),"consolidated":None if consolidated in {None,"unknown"} else consolidated == "true","statements":statements,"structured_observations":structured,"functional_expense_allocations":allocations})
    return reports,metrics,unbound

def adapt_rc4_fixture(rc4: dict, template: dict, context: ReleaseContext) -> dict:
    """Map governed RC4 statement structure into a supplied 0.5 card shape.

    The template supplies only approved target release/domain choices; source rows
    are always reconstructed from the RC4 input and no subject-specific branch is used.
    """
    card = deepcopy(template)
    card.pop("source_statement_fixture", None)
    card["release"] = context.model_dump(exclude={"capability_registry"})
    record = next((x for x in rc4.get("financial_records", []) if x.get("statements")), None)
    if record:
        source_id = card["financial_reports"][0]["source_record_id"]
        period = {"label": card["financial_reports"][0]["reporting_period"].get("label")}
        prior={x["statement_type"]: x for x in card["financial_reports"][0].get("statements", [])}; statements=[]
        for source in record["statements"]:
            if source["statement_type"] not in {"profit_and_loss", "financial_position"}: continue
            statements.append({"statement_id": prior.get(source["statement_type"], {}).get("statement_id", f"stmt:{card['causebase_id']}:{source['statement_type']}"), "statement_type": source["statement_type"], "printed_title": source["statement_title"], "reporting_period": period, "reporting_scope": source.get("reporting_scope", "unknown"), "currency": source.get("currency"), "source_location": None, "rows": [_row(row, card["causebase_id"], source_id, period) for row in source["rows"]]})
        card["financial_reports"][0]["statements"] = statements
    return card

def adapt_rc4_card(rc4_card: dict, source_records: dict[str, dict], capability_registry: CapabilityRegistry, release_context: ReleaseContext) -> dict:
    """Adapt one RC4 public card without a target template or fixture input.

    This deliberately fails closed for legacy display observations that have no
    evidence binding: inventing provenance or silently deleting them would both
    violate the approved v0.5 migration rules.
    """
    evidence=[{"evidence_id": x["evidence_id"], "title": x["title"], **({"url":x["url"]} if x.get("url") else {})} for x in rc4_card.get("evidence", [])]
    source_refs=[]
    for item in [*rc4_card.get("source_native_records", []), *rc4_card.get("source_resolutions", [])]:
        source_id=item["source_record_id"]
        if source_id in source_records and source_id not in source_refs:
            source_refs.append(source_id)
    public_sources=[source_records[x] for x in source_refs]
    unbound={"activities":[],"beneficiaries":[],"descriptive_geography":[],"classifications":[],"funding_sources":rc4_card.get("funding_sources",[]),"fundraising_methods":rc4_card.get("fundraising_methods",[]),"financial_records":[]}
    def observations(legacy_field: str, target: str):
        values=[]
        for ordinal,item in enumerate(rc4_card.get(legacy_field, [])):
            value=item.get("value")
            evidence_ids=item.get("evidence_ids",[])
            recovered=recover_exact(value,public_sources) if not evidence_ids and value else None
            if not evidence_ids and not recovered:
                unbound[target].append(item); continue
            source_ids=[recovered["source_record_id"]] if recovered else []
            recovered_evidence=[]
            if recovered:
                evidence_id=f"ev:rc4-recovery:{rc4_card['causebase_id']}:{target}:{ordinal}"
                evidence.append({"evidence_id":evidence_id,"title":f"Exact public RC4 source-field recovery at {recovered['source_location']}"})
                recovered_evidence=[evidence_id]
            values.append({"observation_id":f"obs:rc4:{rc4_card['causebase_id']}:{target}:{ordinal}","label":value,"claim_basis":"direct","extraction_method":"deterministic_parser" if recovered else "manual","source_record_ids":source_ids,"evidence_ids":evidence_ids or recovered_evidence,"warnings":[f"Recovered from {recovered['source_location']}" ] if recovered else []})
        return values
    activities=observations("activity_observations","activities")
    beneficiaries=observations("beneficiary_observations","beneficiaries")
    geography=observations("geography_observations","descriptive_geography")
    classifications=[]
    for ordinal,item in enumerate(rc4_card.get("classifications",[])):
        evidence_ids=item.get("evidence_ids",[])
        # An exact term-label match alone is not a recoverable classification:
        # it lacks the required deterministic taxonomy mapping rule.
        if not evidence_ids:
            unbound["classifications"].append(item); continue
        classifications.append({"observation_id":f"obs:rc4:{rc4_card['causebase_id']}:classification:{ordinal}","classification_id":f"cls:rc4:{rc4_card['causebase_id']}:{ordinal}","taxonomy_id":item["taxonomy_id"],"taxonomy_version":item["taxonomy_version"],"term_id":item["term_id"],"term_label":item["term_label"],"claim_basis":"direct" if item.get("assignment_method")=="source_native" else "inferred","extraction_method":"llm" if item.get("assignment_method")=="llm_classification" else "deterministic_parser","source_record_ids":[],"evidence_ids":evidence_ids,"confidence":item.get("confidence"),"warnings":[]})
    participation=[]
    for ordinal,item in enumerate(rc4_card.get("participation_observations",[])):
        participation.append({"observation_id":f"obs:rc4:{rc4_card['causebase_id']}:participation:{ordinal}","participation_id":f"part:rc4:{rc4_card['causebase_id']}:{ordinal}","mode":item["mode"],"label":item["label"],"action_url":item.get("action_url"),"status":item.get("status","unknown"),"claim_basis":"direct","extraction_method":"document_text","source_record_ids":[],"evidence_ids":item.get("evidence_ids",[]),"observed_at":item.get("observed_at"),"warnings":[]})
    programs=[]
    for item in rc4_card.get("programs",[]):
        programs.append({"observation_id":f"obs:rc4:{rc4_card['causebase_id']}:program:{item['program_id']}","program_id":item["program_id"],"name":item["name"],"description":item.get("description"),"url":item.get("source_url"),"status":item.get("status","unknown"),"claim_basis":"direct","extraction_method":"api","source_record_ids":[],"evidence_ids":item.get("evidence_ids",[]),"time":{"reporting_period":{"label":item.get("reporting_period")}},"warnings":[]})
    identity={"legal_name":rc4_card["legal_name"],"display_name":rc4_card["display_name"],"operating_names":rc4_card.get("operating_names",[]),"former_names":rc4_card.get("former_names",[]),"entity_status":rc4_card.get("entity_status"),"website":rc4_card.get("website"),"external_identifiers":[{"scheme":x["scheme"],"value":x["value"],"evidence_ids":[x["source_evidence_id"]] if x.get("source_evidence_id") else []} for x in rc4_card.get("external_identifiers",[])],"registrations":[{"regulator":x["regulator"],"status":x.get("status"),"evidence_ids":x.get("evidence_ids",[])} for x in rc4_card.get("registrations",[])],"tax_statuses":[{"scheme":x["scheme"],"status":x.get("status"),"evidence_ids":x.get("evidence_ids",[])} for x in rc4_card.get("tax_statuses",[])]}
    reports,canonical_metrics,unbound_financial=_financial_reports(rc4_card,source_records)
    unbound["financial_records"]=unbound_financial
    legacy_coverage={x["capability"]:x for x in rc4_card.get("coverage",[])}
    aliases={"regulatory.acnc_profile":"regulatory","regulatory.ais":"latest_acnc_ais","web.website":"website","report.annual_report":"annual_report","financial.report":"financials","financial.statements":"financials","fundraising.expenditure":"fundraising_expenditure"}
    coverage=[]
    legacy_only_capabilities={
        "understanding.activities":"activities",
        "understanding.beneficiaries":"beneficiaries",
        "understanding.geography":"descriptive_geography",
        "taxonomy.causebase":"classifications",
        "funding.sources":"funding_sources",
        "fundraising.methods":"fundraising_methods",
        "financial.report":"financial_records",
        "financial.statements":"financial_records",
    }
    for cap in capability_registry.capabilities:
        legacy=legacy_coverage.get(aliases.get(cap.capability_id,""))
        if cap.capability_id in {"financial.report","financial.statements"} and reports:
            status="observed"
        elif cap.capability_id in legacy_only_capabilities and unbound[legacy_only_capabilities[cap.capability_id]]:
            status="unknown"
        else:
            status=legacy["status"] if legacy else "not_yet_processed"
        coverage.append({"capability":cap.capability_id,"status":status,"assessed_at":(legacy.get("observed_at") if legacy else release_context.generated_at),"source_record_ids":[legacy["source_record_id"]] if legacy and legacy.get("source_record_id") else [],"evidence_ids":legacy.get("evidence_ids",[]) if legacy else []})
    legacy=legacy_unbound(release_context.based_on_release,rc4_card,unbound)
    summary_assessment=next((x for x in rc4_card.get("derivative_assessments",[]) if x.get("derivative")=="summary"),None)
    summary=None; derivatives=[]
    if summary_assessment and rc4_card.get("causebase_summary"):
        derivative_id=f"der:rc4:{rc4_card['causebase_id']}:summary"
        summary={"derivative_id":derivative_id,"text":rc4_card["causebase_summary"]}
        derivatives=[{"derivative_id":derivative_id,"kind":"summary","input_observation_ids":[],"evidence_ids":rc4_card.get("summary_evidence_ids",[]),"generated_under":{"output_contract_version":summary_assessment.get("assessment_method","rc4 historical output"),"input_hash":summary_assessment["input_hash"],"generated_at":summary_assessment["generated_at"]},"current_assessment":{"assessed_at":summary_assessment["last_assessed_at"],"assessed_against_contract":"0.5","governing_input_hash":summary_assessment["input_hash"],"disposition":summary_assessment["disposition"],"reason":summary_assessment.get("reason")}}]
    card={"causebase_id":rc4_card["causebase_id"],"contract_version":"0.5","subject_kind":rc4_card["subject_kind"],"identity":identity,"release":release_context.model_dump(exclude={"capability_registry"}),"source_record_refs":source_refs,"source_bindings":[{"source_record_id":x["source_record_id"],"resolution_status":x["resolution_status"],"resolution_basis":x.get("resolution_basis"),"confidence":x["confidence"],"review_status":x["review_status"],"conflicting_signals":x.get("conflicting_signals",[])} for x in rc4_card.get("source_resolutions",[])],"evidence":evidence,"summary":summary,"activities":activities,"beneficiaries":beneficiaries,"descriptive_geography":geography,"navigation_geography":rc4_card.get("navigation_geography",[]),"funding_sources":[],"fundraising_methods":[],"participation":participation,"opportunities":[],"programs":programs,"relationships":[],"classifications":classifications,"coverage":{"registry_id":capability_registry.registry_id,"current":coverage},"financial_reports":reports,"canonical_metrics":canonical_metrics,"analytic_projections":[],"derivatives":derivatives}
    if legacy: card["legacy_unbound"]=legacy
    return card

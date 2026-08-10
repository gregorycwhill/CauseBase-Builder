"""Private facet-purity normalisation of existing taxonomy pressure findings."""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from .models import CauseBaseCard
from .openai_client import estimate_response_cost, responses_create

PROMPT_VERSION="taxonomy-normalisation-0.1"
TARGET_IDS={"P1_add_cause.biodiversity_invasive_species","P2_add_cause.aged_care_elder_support","P3_add_cause.early_years_youth_development","P4_add_beneficiary.children_and_families","P5_add_beneficiary.older_people","P6_add_activity.education_training","P7_add_participation.membership_and_donations","P8_deprecate_cause.employment_inclusion"}

def _hash(x:Any)->str:return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def _schema(name:str)->dict:
    return {"type":"json_schema","name":name,"strict":True,"schema":{"type":"object","additionalProperties":False,"properties":{"findings":{"type":"array","items":{"type":"object","additionalProperties":False,"properties":{"original_proposal_id":{"type":"string"},"finding_status":{"type":"string","enum":["survives","recast","no_change","watch","reject"]},"facet_analysis":{"type":"array","items":{"type":"object","additionalProperties":False,"properties":{"concept":{"type":"string"},"dimension":{"type":"string"},"already_covered":{"type":"string"}},"required":["concept","dimension","already_covered"]}},"normalised_options":{"type":"array","items":{"type":"string"}},"recommendation":{"type":"string"},"representative_subject_ids":{"type":"array","items":{"type":"string"}},"counterexamples":{"type":"array","items":{"type":"string"}},"information_value":{"type":"string"},"migration_impact":{"type":"string"},"confidence":{"type":"string","enum":["high","medium","low"]}},"required":["original_proposal_id","finding_status","facet_analysis","normalised_options","recommendation","representative_subject_ids","counterexamples","information_value","migration_impact","confidence"]}},"dimension_design_questions":{"type":"array","items":{"type":"string"}},"global_observations":{"type":"array","items":{"type":"string"}}},"required":["findings","dimension_design_questions","global_observations"]}}

def _call(model,prompt,schema):
 r=responses_create(model=model,input_text=prompt,text_format=schema,max_output_tokens=20000,max_attempts=1,timeout_seconds=300,reasoning={"effort":"high"})
 if r.status not in {"completed",None}: raise ValueError(f"normalisation incomplete: {r.status}")
 out=json.loads(r.output_text)
 return out,{"response_id":r.response_id,"model":r.model,"reasoning_effort":"high","input_tokens":r.usage.input_tokens,"output_tokens":r.usage.output_tokens,"estimated_cost_usd":str(estimate_response_cost(r.model,r.usage)) if estimate_response_cost(r.model,r.usage) is not None else None}

def run_normalisation(review_path:Path, corpus_path:Path, output_dir:Path, model="gpt-5.6-sol"):
 review=json.loads(review_path.read_text(encoding="utf-8"))["taxonomy_review"]
 proposals=[x for x in review["proposals"] if x["proposal_id"] in TARGET_IDS]
 if {x["proposal_id"] for x in proposals}!=TARGET_IDS: raise ValueError("expected four HIGH, three MEDIUM and WATCH pressure findings")
 cards={x["causebase_id"]:CauseBaseCard.model_validate(x) for x in json.loads(corpus_path.read_text(encoding="utf-8"))["entities"]}
 ids=sorted({i for p in proposals for i in p["representative_subject_ids"]})
 evidence=[{"causebase_id":i,"summary":cards[i].causebase_summary,"activities":cards[i].activities,"beneficiaries":cards[i].beneficiaries,"participation_modes":cards[i].participation_modes,"geography":cards[i].geography} for i in ids if i in cards]
 packet={"baseline":{"version":review["baseline_taxonomy_version"],"dimensions":["cause_problem","beneficiary","activity","approach","participation","geography","organisational_character"]},"pressure_findings":proposals,"representative_derived_evidence":evidence}
 prompt="""You are CauseBase's ontology normaliser. These are pressure findings, not canonical terms. Audit every finding for facet purity. A term must express one independently combinable distinction in its stated dimension. Prefer composition over compounds; do not require a cause term; distinguish age beneficiaries from service fields, education domain from training activity, membership relationship from participation, and donations from participation. Never encode regulator status. Explicitly test phrase fossilisation, corpus overfitting and counterexamples. Do not alter the seven dimensions or taxonomy. Return a human governance analysis for every input finding.

Be concise: at most two facet items, two normalised options, two representative IDs and two counterexamples per finding; each string must be one short sentence. Do not restate the packet.

PACKET:
"""+json.dumps(packet,ensure_ascii=False)
 primary,t1=_call(model,prompt,_schema("causebase_taxonomy_normalisation"))
 if {x["original_proposal_id"] for x in primary["findings"]}!={x["proposal_id"] for x in proposals}: raise ValueError("normaliser did not assess every pressure finding")
 critique_prompt="""Act as an adversarial ontology reviewer. Examine the proposed facet-purity analysis below. Find conceptual flaws, unnecessary compounds, facet leakage, corpus overfitting and plausible counterexamples. For every original pressure finding, return a revised judgement. Only mark survives where a facet-pure, well-defined candidate change remains; otherwise recast, no_change, watch or reject. Do not modify taxonomy.

Be concise: at most two facet items, two normalised options, two representative IDs and two counterexamples per finding; each string must be one short sentence. Do not restate the analysis.

ANALYSIS:
"""+json.dumps(primary,ensure_ascii=False)
 critique,t2=_call(model,critique_prompt,_schema("causebase_taxonomy_adversarial_critique"))
 if {x["original_proposal_id"] for x in critique["findings"]}!={x["proposal_id"] for x in proposals}: raise ValueError("adversarial critique did not assess every pressure finding")
 telemetry={"model":model,"reasoning_effort":"high","prompt_version":PROMPT_VERSION,"calls":[t1,t2]}
 telemetry["total_input_tokens"]=sum(x["input_tokens"] or 0 for x in telemetry["calls"]); telemetry["total_output_tokens"]=sum(x["output_tokens"] or 0 for x in telemetry["calls"]); telemetry["total_estimated_cost_usd"]=str(sum((Decimal(x["estimated_cost_usd"]) for x in telemetry["calls"] if x["estimated_cost_usd"]),Decimal("0")))
 result={"facet_purity_normalisation":{"review_version":"0.1","prompt_version":PROMPT_VERSION,"source_review_hash":_hash(review),"baseline_taxonomy_version":review["baseline_taxonomy_version"],"model":model,"reasoning_effort":"high","generated_at":datetime.now(timezone.utc).isoformat(),"primary_analysis":primary,"adversarial_critique":critique,"surviving_for_human_governance":[x for x in critique["findings"] if x["finding_status"]=="survives"]}}
 output_dir.mkdir(parents=True,exist_ok=True); (output_dir/"facet-purity-normalisation.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8"); (output_dir/"facet-purity-private-telemetry.json").write_text(json.dumps(telemetry,ensure_ascii=False,indent=2),encoding="utf-8")
 lines=["# CauseBase Taxonomy Review v0.1 — Facet Purity / Proposal Normalisation","","Private governed package. No taxonomy, cards, embeddings or Viewer data changed.","",f"Model: `{model}`; reasoning effort: `xhigh`.","","## Surviving proposals"]
 for x in result["facet_purity_normalisation"]["surviving_for_human_governance"]: lines += [f"### {x['original_proposal_id']}",f"- Recommendation: {x['recommendation']}",f"- Options: {'; '.join(x['normalised_options'])}",f"- Counterexamples: {'; '.join(x['counterexamples']) or 'none'}",""]
 lines += ["## All findings","",json.dumps(critique,ensure_ascii=False,indent=2),"",f"Private API cost: USD {telemetry['total_estimated_cost_usd']}"]
 (output_dir/"facet-purity-normalisation-report.md").write_text("\n".join(lines),encoding="utf-8")
 return result

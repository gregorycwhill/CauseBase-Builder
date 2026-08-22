import json
from datetime import datetime, timezone
from pathlib import Path

from charitygraph.models import CauseBaseCard, Classification
from charitygraph.openai_client import ApiResult, ApiUsage
from charitygraph.taxonomy_workflow import HumanDecision, model_review, prepare_review, render_decisions, validate_implemented_change


def _taxonomy():
    return json.loads(Path("config/taxonomies/charitygraph-v0.json").read_text(encoding="utf-8"))


def _corpus():
    card=CauseBaseCard(causebase_id="cb_test",legal_name="Name",display_name="Name",entity_status="registered",causebase_summary="Restores habitat with volunteers.",activities=["habitat restoration"],beneficiaries=["local community"],dataset_version="test",built_at=datetime(2026,1,1,tzinfo=timezone.utc),classifications=[Classification(taxonomy_id="charitygraph",taxonomy_version="0.1-phase2a",term_id="activity.environmental_restoration",term_label="Environmental restoration",assignment_method="llm_classification",confidence="medium"),Classification(taxonomy_id="acnc-register",taxonomy_version="x",term_id="purpose.environment",term_label="Environment",assignment_method="source_native")])
    return {"entities":[card.model_dump(mode="json")]}


def test_prepare_is_deterministic_non_mutating_and_api_free(tmp_path: Path):
    corpus, taxonomy = _corpus(), _taxonomy(); corpus_path=tmp_path/"corpus.json"; tax_path=tmp_path/"tax.json"; corpus_path.write_text(json.dumps(corpus)); tax_path.write_text(json.dumps(taxonomy))
    before_tax=json.dumps(taxonomy,sort_keys=True); before_cards=json.dumps(corpus,sort_keys=True)
    first=prepare_review(corpus_path=corpus_path,taxonomy_path=tax_path,output_dir=tmp_path/"one")
    second=prepare_review(corpus_path=corpus_path,taxonomy_path=tax_path,output_dir=tmp_path/"two")
    assert first["review_summary"]["input_hashes"] == second["review_summary"]["input_hashes"]
    assert json.dumps(taxonomy,sort_keys=True)==before_tax and json.dumps(corpus,sort_keys=True)==before_cards
    assert (tmp_path/"one"/"decision-record.json").read_text().strip()=="[]"
    assert "purpose.environment" not in json.dumps(first["review_summary"]["taxonomy_pressure_signals"])
    assert len(first["review_summary"]["representative_cases"]) <= 40
    assert first["review_summary"]["change_since_previous_review"] is None


def test_decision_and_validate_are_non_mutating(tmp_path: Path):
    corpus, taxonomy = _corpus(), _taxonomy(); cp=tmp_path/"c.json"; bp=tmp_path/"b.json"; cand=tmp_path/"n.json"; decisions=tmp_path/"d.json"; cp.write_text(json.dumps(corpus)); bp.write_text(json.dumps(taxonomy)); candidate=dict(taxonomy); candidate["version"]="0.2"; candidate["terms"]=taxonomy["terms"]+[{'term_id':'activity.example','label':'Example'}]; cand.write_text(json.dumps(candidate))
    decision=HumanDecision(decision_id="d1",review_id="r1",decision_date="2026-08-11",taxonomy_baseline_version="0.1-phase2a",pressure_ids=["q1"],disposition="approve",approved_semantic_decision="Add example",rationale="Test",migration_implications="Reclassify",resulting_taxonomy_version="0.2")
    decisions.write_text(json.dumps([decision.model_dump(mode="json")]))
    result=validate_implemented_change(corpus_path=cp,baseline_taxonomy_path=bp,candidate_taxonomy_path=cand,decision_record_path=decisions,output_path=tmp_path/"report.json")
    assert result["validation"]["terms_added"]==["activity.example"]
    assert result["validation"]["non_mutating"] is True


def test_model_review_is_optional_advisory_and_does_not_write_decisions(tmp_path: Path, monkeypatch):
    corpus, taxonomy = _corpus(), _taxonomy(); cp=tmp_path/"c.json"; tp=tmp_path/"t.json"; cp.write_text(json.dumps(corpus)); tp.write_text(json.dumps(taxonomy))
    prepare_review(corpus_path=cp, taxonomy_path=tp, output_dir=tmp_path/"prepared")
    def fake_response(**kwargs):
        assert "purpose.environment" not in kwargs["input_text"]
        return ApiResult("private-id", "gpt-test", "completed", json.dumps({"advisory_findings": ["inspect boundary"], "counterexamples": [], "limitations": ["small corpus"], "human_questions": ["decide"]}), ApiUsage(10, 20, 30))
    monkeypatch.setattr("charitygraph.taxonomy_workflow.responses_create", fake_response)
    result=model_review(review_summary_path=tmp_path/"prepared"/"review-summary.json", output_dir=tmp_path/"advisory", model="gpt-test")
    assert result["model_review"]["advisory_only"] is True
    assert not (tmp_path/"advisory"/"decision-record.json").exists()
    assert (tmp_path/"prepared"/"decision-record.json").read_text().strip()=="[]"


def test_decision_markdown_and_previous_workflow_comparison(tmp_path: Path):
    corpus, taxonomy = _corpus(), _taxonomy(); cp=tmp_path/"c.json"; tp=tmp_path/"t.json"; cp.write_text(json.dumps(corpus)); tp.write_text(json.dumps(taxonomy))
    prepare_review(corpus_path=cp, taxonomy_path=tp, output_dir=tmp_path/"prior")
    result=prepare_review(corpus_path=cp, taxonomy_path=tp, output_dir=tmp_path/"next", previous_review=tmp_path/"prior")
    assert result["review_summary"]["change_since_previous_review"]["status"] == "compared"
    decision=HumanDecision(decision_id="d1",review_id="r1",decision_date="2026-08-11",taxonomy_baseline_version="0.1-phase2a",pressure_ids=["q1"],disposition="watch",approved_semantic_decision="No change",rationale="More evidence",migration_implications="None")
    record=tmp_path/"decisions.json"; record.write_text(json.dumps([decision.model_dump(mode="json")]))
    render_decisions(decision_record_path=record, output_path=tmp_path/"decisions.md")
    assert "No change" in (tmp_path/"decisions.md").read_text()

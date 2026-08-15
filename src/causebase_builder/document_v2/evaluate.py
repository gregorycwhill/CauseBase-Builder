"""Golden Corpus v1 ecosystem benchmark with computed document-gate state."""
from __future__ import annotations
import json, time
from pathlib import Path
from ..golden import load_corpus, resolve_document
from .adapters import available_candidates, extract_candidate
from .financial import reconstruct_statements, score_eja_statements

SHORTLIST=("pdfplumber", "pymupdf", "camelot-stream", "camelot-lattice", "tesseract", "rapidocr")

def _document_cases(corpus: dict) -> list[dict]:
    seen=set(); cases=[]
    for case in corpus["cases"]:
        key=case.get("source_sha256")
        if key and key not in seen: seen.add(key); cases.append(case)
    return cases

def _text_score(case: dict, result: dict) -> dict:
    markers=case.get("expected", {}).get("required_labels", [])
    text="\n".join(page.get("text", "") for page in result.get("pages", []))
    return {"required_markers": len(markers), "found_markers": [m for m in markers if m.casefold() in text.casefold()], "page_count": result.get("document", {}).get("page_count"), "table_count": sum(len(p.get("tables", [])) for p in result.get("pages", []))}

def _compute_decision(financial: dict, ocr: dict, visual: dict, runs: list[dict]) -> tuple[str, list[str]]:
    if not financial.get("profit_and_loss", {}).get("passed") or not financial.get("financial_position", {}).get("passed"):
        return "failed", ["the primary financial route does not preserve accepted EJA statements"]
    reasons=[]
    if not ocr["passed"]: reasons.append("no actual OCR candidate recovered a low-text Golden Corpus page")
    if not visual["passed"]: reasons.append("the EJA 4/4 visual allocation route is not yet validated")
    if any(run["status"] not in {"completed", "not_applicable"} for run in runs): reasons.append("one or more retained documents lack an explicit completed/failure result")
    return ("decisive" if not reasons else "conditional"), reasons

def _markdown_report(report: dict) -> str:
    lines=["# Golden Corpus v1 document ecosystem benchmark", "", f"**Computed document decision:** {report['decision_classification'].upper()}", "", "| Candidate | Version | Kind | Completed documents | Mean seconds |", "| --- | --- | --- | ---: | ---: |"]
    lines.extend(f"| {name} | {x['version']} | {x['kind']} | {x['runs']} | {x['mean_seconds']} |" for name,x in report["aggregate"].items())
    lines.extend(["", "## Hard gates", "", f"- EJA profit & loss: **{'PASS' if report['financial']['profit_and_loss']['passed'] else 'FAIL'}** ({report['financial']['profit_and_loss']['actual_rows']}/{report['financial']['profit_and_loss']['expected_rows']} rows)", f"- EJA financial position: **{'PASS' if report['financial']['financial_position']['passed'] else 'FAIL'}** ({report['financial']['financial_position']['actual_rows']}/{report['financial']['financial_position']['expected_rows']} rows)", f"- Actual OCR on low-text page: **{'PASS' if report['ocr']['passed'] else 'FAIL'}**", f"- EJA visual allocation 4/4: **{'PASS' if report['visual']['passed'] else 'NOT VALIDATED'}**", "", "## Decision reasons", ""])
    lines.extend([f"- {reason}" for reason in report["decision_reasons"]] or ["- All hard gates passed."])
    return "\n".join(lines)+"\n"

def run_benchmark(corpus_path: Path, *, archive_root: Path | None, runtime_root: Path, gold_card: Path | None = None) -> dict:
    corpus=load_corpus(corpus_path); inventory=available_candidates(); runs=[]
    for case in _document_cases(corpus):
        document, reason=resolve_document(case, archive_root)
        for candidate in SHORTLIST:
            if not document: runs.append({"case_id":case["case_id"],"candidate":candidate,"status":"skipped","reason":reason}); continue
            start=time.perf_counter()
            try:
                result=extract_candidate(document,candidate,cache_root=runtime_root)
                runs.append({"case_id":case["case_id"],"candidate":candidate,"status":result["status"],"seconds":round(time.perf_counter()-start,3),"score":_text_score(case,result),"result":result})
            except Exception as exc: runs.append({"case_id":case["case_id"],"candidate":candidate,"status":"failed","seconds":round(time.perf_counter()-start,3),"reason":f"{type(exc).__name__}: {exc}"})
    eja=next((r for r in runs if r["case_id"]=="eja-financial-statements" and r["candidate"]=="pdfplumber" and r["status"]=="completed"),None)
    financial={"profit_and_loss":{"passed":False,"actual_rows":0,"expected_rows":33},"financial_position":{"passed":False,"actual_rows":0,"expected_rows":32}}
    if eja and gold_card: financial=score_eja_statements(reconstruct_statements(eja["result"]),gold_card)
    ocr_success=[r for r in runs if r["candidate"] in {"tesseract","rapidocr"} and r["status"]=="completed" and any(p.get("route") in {"tesseract","rapidocr"} and len(p.get("text","").strip())>=40 for p in r["result"].get("pages",[]))]
    ocr={"passed":bool(ocr_success),"successful_runs":[{"candidate":r["candidate"],"case_id":r["case_id"]} for r in ocr_success]}
    visual={"passed":False,"status":"external_vision_not_authorized","expected":{"Legal Programs":50,"Operations & Management":31,"Campaigns & Communications":9,"Fundraising":10}}
    compact=[{k:v for k,v in r.items() if k!="result"} for r in runs]
    decision,reasons=_compute_decision(financial,ocr,visual,compact)
    aggregate={}
    for candidate in SHORTLIST:
        finished=[r for r in runs if r["candidate"]==candidate and r["status"]=="completed"]
        aggregate[candidate]={"version":inventory[candidate]["version"],"kind":inventory[candidate]["kind"],"runs":len(finished),"mean_seconds":round(sum(r["seconds"] for r in finished)/len(finished),3) if finished else None}
    report={"corpus_version":corpus["corpus_version"],"shortlist":{c:inventory[c] for c in SHORTLIST},"document_runs":compact,"aggregate":aggregate,"financial":financial,"ocr":ocr,"visual":visual,"decision_classification":decision,"decision_reasons":reasons}
    runtime_root.mkdir(parents=True,exist_ok=True); (runtime_root/"golden-corpus-v1-ecosystem-results.json").write_text(json.dumps(report,indent=2),encoding="utf8"); (runtime_root/"golden-corpus-v1-ecosystem-results.md").write_text(_markdown_report(report),encoding="utf8")
    return report

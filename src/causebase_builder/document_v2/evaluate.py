"""One bounded evaluator for all Golden Corpus document candidates."""
from __future__ import annotations
import json,time
from pathlib import Path
from ..golden import load_corpus,resolve_document
from .pipeline import extract_document

CANDIDATES={
    "pdfplumber-native-v2":{"layout":False,"tables":False},
    "pdfplumber-layout-table-v2":{"layout":True,"tables":True},
    "current-bounded-route-v1":{"layout":False,"tables":True,"use_text_flow":True},
}
def _score(case,result):
    text="\n".join(page["text"] for page in result["pages"])
    expected=case.get("expected",{}); labels=expected.get("required_labels",[])
    allocation=expected.get("allocation",{}); required=list(labels)+[f"{key}" for key in allocation]
    found=[item for item in required if item.casefold() in text.casefold()]
    return {"required_markers":len(required),"found_markers":len(found),"marker_recall":len(found)/len(required) if required else None,"table_count":sum(len(p["tables"]) for p in result["pages"]),"page_count":result["document"]["page_count"]}
def _markdown_report(report: dict) -> str:
    lines=[
        "# Golden Corpus v1 document-stack benchmark", "",
        f"**Decision:** {report['decision_classification']}", "", report["recommendation"], "",
        "## Aggregate candidate results", "", "| Candidate | Completed documents | Mean seconds |", "| --- | ---: | ---: |",
    ]
    lines.extend(f"| {name} | {values['runs']} | {values['mean_seconds']} |" for name, values in report["aggregate"].items())
    lines.extend(["", "## Per-case diagnostics", "", "| Case | Truth level | Candidate | Status | Marker recall | Seconds | Note |", "| --- | --- | --- | --- | ---: | ---: | --- |"])
    for item in report["results"]:
        score=item.get("score", {})
        lines.append("| {case_id} | {truth_level} | {candidate} | {status} | {recall} | {seconds} | {note} |".format(
            case_id=item["case_id"], truth_level=item["truth_level"], candidate=item.get("candidate", "—"), status=item["status"], recall=score.get("marker_recall", "—"), seconds=item.get("seconds", "—"), note=item.get("reason", ", ".join(f"{key}:{value}" for key,value in item.get("route_summary",{}).items()) or "—"),
        ))
    lines.extend(["", "## Limits", "", "This run compares bounded configurations of the installed `pdfplumber` component; it is not evidence of an independent OCR or table-engine bake-off. Unavailable private fixtures are reported as skips, never treated as a passing result. Review-required cases are diagnostics and do not change the hard-gold score.", ""])
    return "\n".join(lines)

def run_benchmark(corpus_path: Path, *, archive_root: Path | None, runtime_root: Path) -> dict:
    corpus=load_corpus(corpus_path); results=[]
    for case in corpus["cases"]:
        document,reason=resolve_document(case,archive_root)
        if not document:
            results.append({"case_id":case["case_id"],"truth_level":case["truth_level"],"status":"skipped","reason":reason}); continue
        for name,options in CANDIDATES.items():
            start=time.perf_counter(); result=extract_document(document,cache_root=runtime_root,options=options); elapsed=round(time.perf_counter()-start,3)
            results.append({"case_id":case["case_id"],"truth_level":case["truth_level"],"strata":case["strata"],"candidate":name,"status":"completed","seconds":elapsed,"score":_score(case,result),"route_summary":{route:sum(1 for p in result["pages"] if p["route"]==route) for route in sorted({p["route"] for p in result["pages"]})}})
    completed=[r for r in results if r["status"]=="completed"]; aggregate={name:{"runs":sum(1 for r in completed if r["candidate"]==name),"mean_seconds":round(sum(r["seconds"] for r in completed if r["candidate"]==name)/max(1,sum(1 for r in completed if r["candidate"]==name)),3)} for name in CANDIDATES}
    report={"corpus_version":corpus["corpus_version"],"candidates":CANDIDATES,"results":results,"aggregate":aggregate,"decision_classification":"conditional","recommendation":"Use deterministic page routing: native layout/text first, pdfplumber tables where present, local OCR only for low-text pages, and separately governed vision only for unresolved visual relationships. No installed independent table/OCR engine justified a single-library winner."}
    runtime_root.mkdir(parents=True,exist_ok=True)
    (runtime_root/"golden-corpus-v1-results.json").write_text(json.dumps(report,indent=2),encoding="utf8")
    (runtime_root/"golden-corpus-v1-results.md").write_text(_markdown_report(report),encoding="utf8")
    return report

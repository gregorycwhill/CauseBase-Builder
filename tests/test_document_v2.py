from pathlib import Path
from PIL import Image, ImageDraw
from causebase_builder.document_v2.pipeline import extract_document
from causebase_builder.document_v2.evaluate import run_benchmark
import json

def test_document_v2_is_cached_and_has_page_provenance(tmp_path):
    image=Image.new("RGB",(300,150),"white"); ImageDraw.Draw(image).text((10,10),"Revenue 100\nExpenses (20)",fill="black"); source=tmp_path/"example.pdf"; image.save(source,"PDF")
    first=extract_document(source,cache_root=tmp_path,options={"tables":True}); second=extract_document(source,cache_root=tmp_path,options={"tables":True})
    assert first["document"]["sha256"]==second["document"]["sha256"] and first["pages"][0]["page"]==1 and second["cache_status"]=="hit"
    assert first["pages"][0]["route"] in {"tesseract","ocr_unavailable","native_text_layout"}

def test_benchmark_emits_machine_and_human_reports(tmp_path):
    corpus={"corpus_version":"1.0","cases":[{"case_id":"sparse","truth_level":"accepted_gold","strata":["sparse"],"expected":{"financials":"absent"}}]}
    manifest=tmp_path/"corpus.json"; manifest.write_text(json.dumps(corpus),encoding="utf8")
    report=run_benchmark(manifest,archive_root=None,runtime_root=tmp_path/"runtime")
    assert report["decision_classification"] == "failed"
    assert (tmp_path/"runtime"/"golden-corpus-v1-ecosystem-results.json").exists()
    assert (tmp_path/"runtime"/"golden-corpus-v1-ecosystem-results.md").exists()

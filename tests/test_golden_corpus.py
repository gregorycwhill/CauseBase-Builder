import json
from pathlib import Path
import pytest
from charitygraph.config import load_paths
from charitygraph.golden import load_corpus, resolve_document

CORPUS = load_paths(Path(__file__).resolve().parents[2]).data_repository_root / "golden" / "corpus-v1.json"
def test_golden_corpus_is_governed_and_has_two_truth_levels():
    corpus=load_corpus(CORPUS); cases=corpus["cases"]
    assert len(cases)==21 and {x["truth_level"] for x in cases}=={"accepted_gold","review_required"}
    assert len({x["case_id"] for x in cases})==len(cases)
    assert any(x["case_id"]=="eja-financial-statements" for x in cases)
def test_missing_archive_fixture_is_a_clear_skip(tmp_path):
    case=next(x for x in load_corpus(CORPUS)["cases"] if x.get("archive_locator"))
    path,reason=resolve_document(case,tmp_path)
    assert path is None and reason=="private_fixture_unavailable"
def test_rejects_candidate_output_as_gold(tmp_path):
    payload={"corpus_version":"1.0","cases":[{"case_id":"x","truth_level":"accepted_gold","strata":[]}]}; path=tmp_path/"bad.json"; path.write_text(json.dumps(payload))
    with pytest.raises(ValueError,match="expected observations"): load_corpus(path)

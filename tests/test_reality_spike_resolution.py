import json
from pathlib import Path

from charitygraph.sources.reality_spike import map_ais_coverage, resolve_cohort, resolve_report_abns


def test_name_only_spike_seeds_remain_candidates_or_ambiguous(tmp_path: Path):
    cohort = tmp_path / "cohort.json"
    cohort.write_text(json.dumps({"status": "test", "candidates": [{"name": "Example"}]}), encoding="utf-8")
    source = tmp_path / "acnc.csv"
    source.write_text(
        "ABN,Charity Legal Name,Charity Name\n51111111111,Example,Example\n",
        encoding="utf-8",
    )
    report = resolve_cohort(cohort, source)
    result = report["results"][0]
    assert result["resolution_status"] == "candidate"
    assert result["confidence"] == "medium"
    assert result["review_status"] == "pending"


def test_ais_mapping_reports_source_coverage_without_resolving_subjects(tmp_path: Path):
    resolution = tmp_path / "resolution.json"
    resolution.write_text(
        json.dumps({"results": [{"seed_name": "Example", "resolution_status": "candidate", "candidates": [{"external_identifiers": [{"scheme": "abn", "value": "51111111111"}]}]}]}),
        encoding="utf-8",
    )
    ais = tmp_path / "ais.csv"
    ais.write_text(
        "ABN,AIS Year,Fin Report From,Fin Report To,Report Consolidated With More Than One Entity,Total Revenue,Total Expenses\n"
        "51111111111,2024-25,01/07/2024,30/06/2025,Y,1,2\n",
        encoding="utf-8",
    )
    row = map_ais_coverage(resolution, ais)["rows"][0]
    assert row["financial_coverage_status"] == "observed"
    assert row["records"][0]["consolidated"] == "true"


def test_report_abn_resolution_uses_disclosed_identifier_not_name(tmp_path: Path):
    extract = tmp_path / "report.json"
    extract.write_text(json.dumps({"source_sha256": "abc", "pages": [{"text": "ABN: 51 111 111 111"}]}), encoding="utf-8")
    register = tmp_path / "acnc.csv"
    register.write_text("ABN,Charity Legal Name,Charity Name\n51111111111,Example,Example\n", encoding="utf-8")
    row = resolve_report_abns([extract], register)["rows"][0]
    assert row["resolution_status"] == "resolved"
    assert row["confidence"] == "high"

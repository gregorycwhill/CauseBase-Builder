import json
from pathlib import Path

from causebase_builder.national import build_national_backbone, validate_structured_backbone


def test_national_backbone_preserves_source_records_without_promoting_candidates(tmp_path: Path):
    acnc = tmp_path / "acnc.csv"
    acnc.write_text("ABN,Charity Legal Name,Charity Name\n51111111111,Example,Example\n", encoding="utf-8")
    ais = tmp_path / "ais.csv"
    ais.write_text("ABN,Fin Report From,Fin Report To,Report Consolidated With More Than One Entity,Total Revenue,Total Expenses\n51111111111,01/10/2024,30/06/2025,Y,1200,1000\n", encoding="utf-8")
    metadata = {"source_id":"test","publisher":"test","source_url":"https://example.test","retrieved_at":"2026-08-10","content_sha256":"abc","licence":"CC BY"}
    (tmp_path / "acnc.json").write_text(json.dumps(metadata), encoding="utf-8")
    (tmp_path / "ais.json").write_text(json.dumps({**metadata, "source_id":"ais"}), encoding="utf-8")
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"registry_version":"0.1","subjects":[]}), encoding="utf-8")
    dgr = tmp_path / "dgr.json"
    dgr.write_text(json.dumps({"source":{"source_id":"dgr"},"observations":[{"abn":"51111111111","dgr_status":"endorsed"}]}), encoding="utf-8")

    diagnostics = build_national_backbone(acnc_csv=acnc, acnc_metadata=tmp_path / "acnc.json", ais_csv=ais, ais_metadata=tmp_path / "ais.json", dgr_observations=dgr, dgr_bulk_zips=None, dgr_metadata=None, registry_path=registry, private_output=tmp_path / "private", public_output=tmp_path / "public")

    rows = [json.loads(line) for line in (tmp_path / "private" / "source-records.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[0]["resolution"]["resolution_status"] == "candidate"
    assert rows[1]["consolidated"] == "true"
    assert rows[1]["money_observations"]["revenue"]["normalised_amount"] == "1200"
    assert diagnostics["reporting_period_distribution"]["nonstandard"] == 1
    assert validate_structured_backbone(tmp_path / "public") == []

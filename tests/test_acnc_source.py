from pathlib import Path

from causebase_builder.sources.acnc import parse_acnc_register_csv


def test_acnc_adapter_uses_stable_source_identity_and_external_ids(tmp_path: Path):
    csv_file = tmp_path / "acnc.csv"
    csv_file.write_text(
        "ACNC Registration Number,ABN,Charity Legal Name,Charity Name,Charity Status\n"
        "1234,51111111111,Example Legal Entity,Example Charity,Registered\n",
        encoding="utf-8",
    )

    [record] = parse_acnc_register_csv(csv_file)

    assert record.source_record_id.startswith("src:acnc-register:")
    assert record.source_record_id != "51111111111"
    assert {(identifier.scheme, identifier.value) for identifier in record.external_identifiers} == {
        ("acnc_registration_id", "1234"),
        ("abn", "51111111111"),
    }


def test_acnc_adapter_skips_unidentifiable_source_rows(tmp_path: Path):
    csv_file = tmp_path / "acnc.csv"
    csv_file.write_text(
        "ABN,Charity Legal Name,Charity Name\n,Unidentifiable,Unidentifiable\n",
        encoding="utf-8",
    )
    assert parse_acnc_register_csv(csv_file) == []

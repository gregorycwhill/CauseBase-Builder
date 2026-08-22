from pathlib import Path

from charitygraph.sources.ais import parse_ais_financial_csv
from charitygraph.sources.dgr import iter_dgr_bulk_extract, parse_dgr_csv


def test_ais_adapter_preserves_reporting_period_and_numeric_source_values(tmp_path: Path):
    source = tmp_path / "ais.csv"
    source.write_text(
        "ABN,AIS Year,Fin Report From,Fin Report To,Total Revenue,Total Expenses\n"
        "51111111111,2024-25,01/07/2024,30/06/2025,1,2\n",
        encoding="utf-8",
    )

    [record] = parse_ais_financial_csv(source)

    assert record.abn == "51111111111"
    assert record.reporting_period == "2024-25"
    assert record.financial_report_from == "01/07/2024"
    assert record.financial_report_to == "30/06/2025"
    assert record.consolidated == "unknown"
    assert record.revenue.normalised_amount == 1
    assert record.total_expenses.normalised_amount == 2


def test_dgr_adapter_preserves_status_without_promoting_it_to_subject_identity(tmp_path: Path):
    source = tmp_path / "dgr.csv"
    source.write_text(
        "Australian Business Number,Deductible Gift Recipient Status,DGR Item\n"
        "51111111111,Yes,Item 1\n",
        encoding="utf-8",
    )

    [record] = parse_dgr_csv(source)

    assert record.abn == "51111111111"
    assert record.dgr_status == "Yes"
    assert record.dgr_item == "Item 1"


def test_ais_adapter_derives_lossless_label_when_source_has_none(tmp_path: Path):
    source = tmp_path / "ais.csv"
    source.write_text(
        "ABN,Fin Report From,Fin Report To\n51111111111,01/01/2023,31/12/2023\n",
        encoding="utf-8",
    )
    [record] = parse_ais_financial_csv(source)
    assert record.reporting_period == "01/01/2023 to 31/12/2023"


def test_dgr_bulk_parser_retains_only_dgr_observations(tmp_path: Path):
    import zipfile

    archive = tmp_path / "bulk.zip"
    xml = "<Transfer><ABR><ABN>51111111111</ABN><DGR><DGRStatus>Y</DGRStatus></DGR></ABR><ABR><ABN>52222222222</ABN></ABR></Transfer>"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("sample.xml", xml)
    records = list(iter_dgr_bulk_extract([archive]))
    assert [record.abn for record in records] == ["51111111111"]
    assert records[0].dgr_status == "endorsed"

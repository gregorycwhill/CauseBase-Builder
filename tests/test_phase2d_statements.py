from decimal import Decimal

from charitygraph.models import Financials
from charitygraph.phase2d import _donations_gifts_bequests, _report_rows, _separate_legacy_provenance, _statements


def test_primary_statement_rows_survive_in_source_order_before_canonical_projection():
    extract = {"pages": [{"page": 8, "text": """Statement of profit or loss
For the year ended 30 June 2025
Revenue
Grants 2,078,583 2,601,030
Donations, Fundraisings, Lectures 2,051,817 1,838,542
5,016,000 5,339,242
Expenses
Employee benefits expense (4,670,344) (4,133,374)
(5,852,789) (5,650,862)
The above statement of profit or loss should be read in conjunction with accompanying notes
"""}]}
    rows = _report_rows(extract)
    statement = _statements(rows, "ev:report:test", {"label": "test"})[0]

    assert statement.statement_type == "profit_and_loss"
    assert [row.source_label for row in statement.rows] == [
        "For the year ended 30 June 2025", "Revenue", "Grants",
        "Donations, Fundraisings, Lectures", "5,016,000 5,339,242",
        "Expenses", "Employee benefits expense", "(5,852,789) (5,650,862)",
    ]
    mixed = statement.rows[3]
    assert mixed.current_amount.normalised_amount == 2051817
    assert mixed.comparative_periods[0].amount.normalised_amount == 1838542
    assert mixed.canonical_metrics == []
    assert statement.rows[6].canonical_metrics == ["employee_costs"]
    assert statement.rows[4].canonical_metrics == ["revenue"]


def test_terminal_source_qualifier_becomes_structured_metadata():
    values, observations = _separate_legacy_provenance([
        "Legal advice and representation (as described by the organisation)",
        "Community legal work (NSW)",
    ])
    assert values == ["Legal advice and representation", "Community legal work (NSW)"]
    assert observations[0].provenance_note == "as described by the organisation"
    assert observations[1].provenance_note is None


def test_reviewed_structured_value_remediation_can_omit_a_misfiled_value():
    values, _ = _separate_legacy_provenance([
        "Website invitation to join as a member of settlement agencies",
        "Advocacy and policy activities",
    ])
    assert values == ["Advocacy and policy activities"]


def test_donations_gifts_bequests_includes_explicit_full_rows_only_and_retains_derivation_contract():
    extract = {"pages": [{"page": 8, "text": """Statement of profit or loss
For the year ended 30 June 2025
Revenue
Donations, Fundraisings, Lectures 2,051,817 1,838,542
Donations - Future Fund 50,000 0
Fees for Service 51,771 40,000
Interest Received 79,883 20,000
5,016,000 5,339,242
Expenses
(5,852,789) (5,650,862)
"""}]}
    rows = _report_rows(extract)
    statements = _statements(rows, "ev:report:test", {"label": "year ended 2025-06-30"})
    total = next(row.current_amount for row in statements[0].rows if "revenue" in row.canonical_metrics and row.current_amount)
    financial = Financials(financial_record_id="fr:test", period={"label": "year ended 2025-06-30"}, reporting_scope="subject", revenue=total, statements=statements)
    projection = _donations_gifts_bequests(financial)
    assert projection.canonical_label == "Donations, gifts & bequests"
    assert [item.source_label for item in projection.components] == ["Donations, Fundraisings, Lectures", "Donations - Future Fund"]
    assert projection.numerator_amount.normalised_amount == Decimal("2101817")
    assert projection.result == Decimal("2101817") / Decimal("5016000")
    assert projection.formula == "reported_revenue_line_divided_by_reported_total_income"
    assert len(projection.component_observation_ids) == 2
    assert projection.denominator_observation_id
    assert projection.reporting_scope == "subject"

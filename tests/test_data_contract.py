from datetime import date

from causebase_builder.models import CoverageObservation, FinancialPeriod, SourceResolution


def test_source_resolution_keeps_ambiguity_and_review_state_explicit():
    resolution = SourceResolution(
        source_record_id="src:acnc-register:test",
        resolution_status="ambiguous",
        resolution_basis="same branded name appears on multiple records",
        confidence="medium",
        conflicting_signals=["two possible ABNs"],
        review_status="pending",
    )
    assert resolution.resolution_status == "ambiguous"
    assert resolution.review_status == "pending"


def test_financial_period_preserves_transition_length_and_coverage_absence():
    period = FinancialPeriod(
        period_start=date(2024, 10, 1),
        period_end=date(2025, 6, 30),
        period_length_days=273,
        label="FY25 (9 months)",
        is_transitional_or_nonstandard=True,
    )
    coverage = CoverageObservation(
        capability="annual_report",
        status="not_found_in_source",
        source_record_id="src:web:test",
    )
    assert period.is_transitional_or_nonstandard
    assert coverage.status == "not_found_in_source"

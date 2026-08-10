from datetime import date

import pytest

from causebase_builder.models import CauseBaseCard, CoverageObservation, FinancialPeriod, SourceResolution


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


def test_card_rejects_duplicate_effective_coverage_capabilities():
    with pytest.raises(ValueError, match="one effective coverage observation"):
        CauseBaseCard(
            causebase_id="cb_test", legal_name="Test", display_name="Test", entity_status="registered",
            causebase_summary="Test", dataset_version="test", built_at="2026-08-10T00:00:00Z",
            coverage=[
                CoverageObservation(capability="website", status="observed"),
                CoverageObservation(capability="website", status="retrieval_failed"),
            ],
        )

from decimal import Decimal

import pytest
from pydantic import ValidationError

from causebase_builder.models import MoneyObservation


def test_ais_raw_dollars_normalise_exactly():
    amount = MoneyObservation(source_amount="184000", source_unit_scale=1, normalised_amount="184000")
    assert amount.normalised_amount == Decimal("184000")


def test_report_thousands_normalise_exactly():
    amount = MoneyObservation(
        source_amount="184", source_unit_scale=1000, normalised_amount="184000", source_unit_label="$ '000"
    )
    assert amount.normalised_amount == Decimal("184000")


def test_negative_and_zero_are_preserved_but_missing_is_not_zero():
    negative = MoneyObservation(source_amount="-72", source_unit_scale=1000, normalised_amount="-72000")
    zero = MoneyObservation(source_amount="0", source_unit_scale=1, normalised_amount="0")
    assert negative.normalised_amount == Decimal("-72000")
    assert zero.normalised_amount == Decimal("0")
    with pytest.raises(ValidationError):
        MoneyObservation(source_amount="184", source_unit_scale=1000, normalised_amount="184")


def test_differently_scaled_sources_share_normalised_value_for_calculation():
    report = MoneyObservation(source_amount="184", source_unit_scale=1000, normalised_amount="184000")
    ais = MoneyObservation(source_amount="184000", source_unit_scale=1, normalised_amount="184000")
    assert report.normalised_amount / ais.normalised_amount == Decimal("1")

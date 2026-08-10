"""Minimal Annual Information Statement CSV adapter for reality-spike finance evidence."""

from __future__ import annotations

import csv
from decimal import Decimal
from dataclasses import dataclass
from pathlib import Path

from .acnc import _value
from ..models import MoneyObservation


def _number(value: str | None) -> Decimal | None:
    if not value:
        return None
    return Decimal(value.replace(",", "").replace("$", ""))


def _money(value: str | None) -> MoneyObservation | None:
    amount = _number(value)
    if amount is None:
        return None
    return MoneyObservation(
        source_amount=amount,
        source_currency="AUD",
        source_unit_scale=1,
        normalised_amount=amount,
        normalised_currency="AUD",
        source_raw_value=value,
    )


def _period_label(value: str | None, start: str | None, end: str | None) -> str | None:
    """Retain a supplied label or a lossless deterministic start/end representation."""
    return value or (f"{start} to {end}" if start and end else None)


@dataclass(frozen=True)
class AisFinancialRecord:
    abn: str
    reporting_period: str | None
    financial_report_from: str | None
    financial_report_to: str | None
    consolidated: str
    revenue: MoneyObservation | None
    total_expenses: MoneyObservation | None
    raw: dict[str, str]


def parse_ais_financial_csv(path: Path) -> list[AisFinancialRecord]:
    """Normalise selected AIS financial fields without interpreting accounting meaning."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    records = []
    for row in rows:
        abn = _value(row, "ABN", "Australian Business Number")
        if not abn:
            raise ValueError("AIS row missing ABN")
        financial_report_from = _value(row, "Financial Report From", "Fin Report From")
        financial_report_to = _value(row, "Financial Report To", "Fin Report To")
        records.append(
            AisFinancialRecord(
                abn=abn,
                reporting_period=_period_label(
                    _value(row, "AIS Reporting Period", "Reporting Period", "Financial Year", "AIS Year"),
                    financial_report_from,
                    financial_report_to,
                ),
                financial_report_from=financial_report_from,
                financial_report_to=financial_report_to,
                consolidated=(
                    "true"
                    if (_value(row, "Report Consolidated With More Than One Entity") or "").lower() in {"y", "yes", "true"}
                    else "false"
                    if (_value(row, "Report Consolidated With More Than One Entity") or "").lower() in {"n", "no", "false"}
                    else "unknown"
                ),
                revenue=_money(_value(row, "Total Revenue", "Revenue", "Total Income")),
                total_expenses=_money(
                    _value(row, "Total Expenses", "Total Expenditure", "Expenses")
                ),
                raw=dict(row),
            )
        )
    return records

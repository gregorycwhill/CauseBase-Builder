from __future__ import annotations

from decimal import Decimal

from .models import FundraisingComponent, FundraisingEstimate, MoneyObservation


def _fixture_observation(value: object) -> MoneyObservation:
    amount = Decimal(str(value))
    return MoneyObservation(
        source_amount=amount,
        source_currency="AUD",
        source_unit_scale=1,
        normalised_amount=amount,
        normalised_currency="AUD",
        source_raw_value=str(value),
    )


def estimate_fundraising(source: dict) -> FundraisingEstimate:
    """Produce the required fundraising estimate using the demo fallback ladder.

    This implements only the first, heuristic, and final fallback branches for the
    vertical slice. LLM and peer-group estimation are intentionally deferred.
    """
    financials = source["financials"]
    period_value = financials.get("period", {})
    period = period_value if isinstance(period_value, str) else period_value.get("label")
    financial_record_id = financials.get("financial_record_id")
    fr = source.get("fundraising", {})

    direct = fr.get("direct")
    if direct is not None:
        return FundraisingEstimate(
            normalised_amount=Decimal(str(direct["value"])),
            normalised_currency="AUD",
            reporting_period_label=period,
            financial_record_id=financial_record_id,
            method="direct_extract",
            confidence="high",
            evidence_ids=list(direct.get("evidence_ids", [])),
            direct_observation=_fixture_observation(direct["value"]),
            note="Explicit fundraising expenditure disclosed by the organisation.",
        )

    heuristic_labels = {
        "marketing",
        "public relations",
        "pr",
        "fundraising events",
        "donor acquisition",
    }
    components = []
    for row in fr.get("expense_components", []):
        if row["label"].strip().lower() in heuristic_labels:
            components.append(
                FundraisingComponent(
                    label=row["label"],
                    amount=_fixture_observation(row["value"]),
                    evidence_ids=list(row.get("evidence_ids", [])),
                )
            )

    if components:
        value = sum((c.amount.normalised_amount for c in components), Decimal("0"))
        evidence_ids = sorted({eid for c in components for eid in c.evidence_ids})
        return FundraisingEstimate(
            normalised_amount=value,
            normalised_currency="AUD",
            reporting_period_label=period,
            financial_record_id=financial_record_id,
            method="heuristic_estimate",
            confidence="medium",
            evidence_ids=evidence_ids,
            components=components,
            rule_id="CB-FUND-H03",
            note="Marketing, public-relations and clearly fundraising-related components included by demo rule CB-FUND-H03.",
        )

    total_expenses = source["financials"].get("total_expenses")
    if total_expenses is None:
        raise ValueError(
            f"{source['causebase_id']}: cannot produce required fundraising estimate; "
            "no direct/component evidence and no total_expenses for fallback prior"
        )

    if isinstance(total_expenses, dict):
        total_expenses = total_expenses["normalised_amount"]
    prior_ratio = Decimal(str(fr.get("fallback_prior_ratio", "0.15")))
    value = Decimal(str(total_expenses)) * prior_ratio
    return FundraisingEstimate(
        normalised_amount=value,
        normalised_currency="AUD",
        reporting_period_label=period,
        financial_record_id=financial_record_id,
        method="fallback_prior",
        confidence="low",
        evidence_ids=list(fr.get("fallback_evidence_ids", [])),
        rule_id="CB-FUND-P01",
        note=(
            f"No usable fundraising disclosure found in the demo evidence. "
            f"Applied fallback prior of {prior_ratio:.0%} of total expenses."
        ),
        plausible_low=value * Decimal("0.6"),
        plausible_high=value * Decimal("1.6"),
    )

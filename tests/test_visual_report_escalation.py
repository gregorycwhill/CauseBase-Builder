from decimal import Decimal

from PIL import Image, ImageDraw

from causebase_builder.models import MoneyObservation
from causebase_builder.phase2d import _functional_expense_allocations
from causebase_builder.sources import documents


def test_visual_expense_allocation_is_generic_complete_and_reconciled():
    extract = {"pages": [{"page": 29, "vision_escalation": {"validation_outcome": "pending_cross_check"}, "visual_observations": [
        {"kind": "functional_expense_allocation", "source_label": "Legal Programs", "share_percent": 50, "page": 29},
        {"kind": "functional_expense_allocation", "source_label": "Operations & Management", "share_percent": 31, "page": 29},
        {"kind": "functional_expense_allocation", "source_label": "Campaigns & Communications", "share_percent": 9, "page": 29},
        {"kind": "functional_expense_allocation", "source_label": "Fundraising", "share_percent": 10, "page": 29},
    ]}]}
    expenses = MoneyObservation(source_amount=Decimal("-5852789"), normalised_amount=Decimal("-5852789"), source_raw_value="(5,852,789)")

    allocations = _functional_expense_allocations(extract, "ev:report:test", expenses)

    assert [item.source_label for item in allocations] == ["Legal Programs", "Operations & Management", "Campaigns & Communications", "Fundraising"]
    assert sum(item.share for item in allocations) == Decimal("1")
    fundraising = allocations[-1]
    assert fundraising.direct_observation is True
    assert fundraising.share == Decimal("0.1")
    assert fundraising.derived_amount.normalised_amount == Decimal("585279")
    assert fundraising.denominator_label == "Total expenses"
    assert fundraising.denominator_amount.normalised_amount == Decimal("-5852789")
    assert fundraising.derived_amount_method == "rounded_percentage_x_reported_total"
    assert fundraising.derived_amount_approximate is True
    assert extract["pages"][0]["vision_escalation"]["validation_outcome"] == "passed_share_sum_and_total_expenses_cross_check"


def test_full_page_image_uses_local_ocr_before_any_vision(monkeypatch, tmp_path):
    image = Image.new("RGB", (1200, 900), "white")
    ImageDraw.Draw(image).text((80, 100), "Income table 2025 2024", fill="black")
    pdf = tmp_path / "scanned-table.pdf"
    image.save(pdf, "PDF")
    monkeypatch.setattr(documents, "_local_ocr", lambda _: ("Income table 2025 2024", None))

    result = documents.extract_pdf_evidence(pdf)

    page = result["pages"][0]
    assert page["native_text_characters"] == 0
    assert "image_only_or_scanned" in page["page_states"]
    assert page["ocr_text"] == "Income table 2025 2024"
    assert page["vision_escalation"] is None


def test_narrow_vision_only_receives_one_unresolved_page(monkeypatch, tmp_path):
    image = Image.new("RGB", (1200, 900), "white")
    ImageDraw.Draw(image).text((80, 100), "Expense chart", fill="black")
    pdf = tmp_path / "scanned-chart.pdf"
    image.save(pdf, "PDF")
    monkeypatch.setattr(documents, "_local_ocr", lambda _: ("Legal Programs 50%\nOperations 31%\nExpense allocation", None))
    calls = []

    def vision(payload):
        calls.append(payload)
        return {"model": "test-narrow-vision", "usage": {"input_tokens": 12}, "cost": 0.01, "observations": [
            {"kind": "functional_expense_allocation", "source_label": "Legal Programs", "share_percent": 50},
            {"kind": "functional_expense_allocation", "source_label": "Operations", "share_percent": 50},
        ]}

    result = documents.extract_pdf_evidence(pdf, vision_extractor=vision)

    page = result["pages"][0]
    assert page["page_state"] == "visual_relationships_unresolved"
    assert len(calls) == 1 and calls[0]["page"] == 1
    assert page["vision_escalation"]["model"] == "test-narrow-vision"
    assert page["vision_escalation"]["cost"] == 0.01

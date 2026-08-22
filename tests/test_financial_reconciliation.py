from pathlib import Path

import pytest
from pydantic import ValidationError

from charitygraph.pipeline import build_fixture_corpus


def test_fundraising_estimate_cannot_reference_unretained_financial_record():
    cards, _, _ = build_fixture_corpus(
        Path("tests/fixtures/source/entities.json"), dataset_version="test-reconciliation"
    )
    payload = cards[0].model_dump(mode="json")
    payload["fundraising_expenditure"]["financial_record_id"] = "fr:missing"
    with pytest.raises(ValidationError, match="unknown financial record"):
        type(cards[0]).model_validate(payload)

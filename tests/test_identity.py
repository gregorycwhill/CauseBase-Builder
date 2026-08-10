from pathlib import Path

from causebase_builder.pipeline import build_fixture_corpus


def test_fixture_cards_use_opaque_causebase_ids_and_external_abns():
    cards, _, _ = build_fixture_corpus(
        Path("tests/fixtures/source/entities.json"), dataset_version="test-identity"
    )

    assert all(card.causebase_id.startswith("cb:demo:") for card in cards)
    assert all(card.external_identifiers for card in cards)
    assert all(
        any(identifier.scheme == "abn" for identifier in card.external_identifiers)
        for card in cards
    )
    assert len({card.causebase_id for card in cards}) == len(cards)

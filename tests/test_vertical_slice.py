import csv
import json
from pathlib import Path

from causebase_builder.pipeline import build_fixture_corpus
from causebase_builder.models import FinancialMetricObservation, MoneyObservation
from causebase_builder.render import card_locator, flatten_card, render_markdown, render_publication
from causebase_builder.validate import validate_publication


def test_fixture_build_round_trip(tmp_path: Path):
    cards, vectors, similarities = build_fixture_corpus(
        Path("tests/fixtures/source/entities.json"),
        dataset_version="test-0.1",
    )

    assert len(cards) == 3
    assert cards[0].fundraising_expenditure is not None
    assert cards[1].fundraising_expenditure is not None
    assert cards[2].fundraising_expenditure is None
    assert all(
        card.fundraising_expenditure is None
        or card.fundraising_expenditure.method not in {"fallback_prior", "peer_imputation"}
        for card in cards
    )
    assert all(card.embedding is not None for card in cards)

    render_publication(
        cards,
        vectors,
        similarities,
        tmp_path,
        require_parquet=False,
    )

    errors = validate_publication(tmp_path)
    assert errors == []

    payload = json.loads((tmp_path / "causebase.json").read_text(encoding="utf-8"))
    assert len(payload["entities"]) == 3
    publication_text = (tmp_path / "causebase.json").read_text(encoding="utf-8").lower()
    assert "fallback_prior" not in publication_text
    assert "peer_imputation" not in publication_text
    assert "midpoint" not in publication_text
    assert "point_estimate" not in publication_text

    with (tmp_path / "causebase.csv").open(encoding="utf-8", newline="") as f:
        csv_rows = list(csv.DictReader(f))
    assert len(csv_rows) == 3

    md = (tmp_path / card_locator(cards[0])).read_text(encoding="utf-8")
    assert "CauseBase summary" in md
    assert "Fundraising estimate method" in md
    assert "Embedding model" in md
    assert "[-0." not in md


def test_publication_can_include_taxonomy_coverage_and_agent_guide(tmp_path: Path):
    cards, vectors, similarities = build_fixture_corpus(
        Path("tests/fixtures/source/entities.json"), dataset_version="test-0.1"
    )
    render_publication(
        cards, vectors, similarities, tmp_path, require_parquet=False,
        taxonomy={"taxonomy_id": "causebase", "version": "test", "terms": []},
        agent_guide="# Retrieval\nUse `causebase.json` to locate a stable card.",
    )

    assert json.loads((tmp_path / "coverage.json").read_text(encoding="utf-8"))["entity_count"] == 3
    assert (tmp_path / "taxonomy" / "causebase-v0.json").exists()
    assert (tmp_path / "agent-guide.md").exists()
    assert validate_publication(tmp_path) == []


def test_similarity_is_descriptive_not_recommendation():
    cards, vectors, similarities = build_fixture_corpus(
        Path("tests/fixtures/source/entities.json"),
        dataset_version="test-0.1",
    )
    assert similarities
    assert all("recommend" not in str(row).lower() for row in similarities)


def test_publication_rejects_unexpected_file(tmp_path: Path):
    cards, vectors, similarities = build_fixture_corpus(
        Path("tests/fixtures/source/entities.json"), dataset_version="test-0.1"
    )
    render_publication(cards, vectors, similarities, tmp_path, require_parquet=False)
    (tmp_path / "unreviewed-source.txt").write_text("must not publish", encoding="utf-8")

    errors = validate_publication(tmp_path)

    assert "unexpected publication artefact: unreviewed-source.txt" in errors


def test_publication_rejects_financial_total_duplicated_across_subject_cards(tmp_path: Path):
    cards, vectors, similarities = build_fixture_corpus(
        Path("tests/fixtures/source/entities.json"), dataset_version="test-0.1"
    )
    cards[1].financial_records[0].financial_record_id = cards[0].financial_records[0].financial_record_id
    cards[1].fundraising_expenditure.financial_record_id = cards[0].financial_records[0].financial_record_id
    for metric in cards[1].financial_metrics:
        metric.observations[0].financial_record_id = cards[0].financial_records[0].financial_record_id
    render_publication(cards, vectors, similarities, tmp_path, require_parquet=False)
    errors = validate_publication(tmp_path)
    assert any(error.startswith("financial record duplicated across public cards") for error in errors)


def test_divergent_metric_never_silently_flattens_to_one_value():
    cards, _, _ = build_fixture_corpus(
        Path("tests/fixtures/source/entities.json"), dataset_version="test-0.1"
    )
    revenue = next(item for item in cards[0].financial_metrics if item.metric == "revenue")
    revenue.observations.append(
        FinancialMetricObservation(
            financial_record_id="fr:other-source",
            amount=MoneyObservation(source_amount="181", source_unit_scale=1000, normalised_amount="181000"),
        )
    )
    revenue.reconciliation_status = "divergent"
    assert flatten_card(cards[0])["revenue"] is None
    assert "Multiple reported values [divergent]" in render_markdown(cards[0])


def test_real_red_cross_conflicting_revenue_is_retained_and_not_flattened():
    cards, _, _ = build_fixture_corpus(
        Path("../CauseBase-Data/governed-inputs/reality-spike/australian-red-cross.json"),
        dataset_version="reality-spike-test",
    )

    card = cards[0]
    revenue = next(metric for metric in card.financial_metrics if metric.metric == "revenue")
    expenses = next(metric for metric in card.financial_metrics if metric.metric == "total_expenses")

    assert revenue.reconciliation_status == "non_comparable"
    assert len(revenue.observations) == 2
    assert flatten_card(card)["revenue"] is None
    assert expenses.reconciliation_status == "agreeing"
    assert len(card.financial_records) == 2


def test_real_merri_transition_and_fitted_identity_evidence_are_retained():
    merri_cards, _, _ = build_fixture_corpus(
        Path("../CauseBase-Data/governed-inputs/reality-spike/merri-creek-management-committee.json"),
        dataset_version="reality-spike-test",
    )
    fitted_cards, _, _ = build_fixture_corpus(
        Path("../CauseBase-Data/governed-inputs/reality-spike/fitted-for-work.json"),
        dataset_version="reality-spike-test",
    )

    assert merri_cards[0].financial_records[0].period.period_length_days == 273
    assert merri_cards[0].financial_records[0].period.is_transitional_or_nonstandard is True
    resolution = fitted_cards[0].source_resolutions[0]
    assert resolution.resolution_status == "resolved"
    assert "ABN:78126256862" in resolution.supporting_signals

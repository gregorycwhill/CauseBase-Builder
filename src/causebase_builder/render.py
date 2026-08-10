from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Iterable

import pandas as pd

from .models import CauseBaseCard


def _jsonable(card: CauseBaseCard) -> dict:
    return card.model_dump(mode="json")


def card_locator(card: CauseBaseCard) -> str:
    """Stable filesystem-safe locator derived from, but not substituting for, identity."""
    digest = hashlib.sha256(card.causebase_id.encode("utf-8")).hexdigest()
    return f"cards/{digest[:2]}/{digest}.md"


def render_markdown(card: CauseBaseCard) -> str:
    fr = card.fundraising_expenditure

    classifications = {}
    for c in card.classifications:
        classifications.setdefault(c.taxonomy_id, []).append(c)

    metric_sets = {item.metric: item for item in card.financial_metrics}
    def display_metric(metric: str) -> str:
        metric_set = metric_sets.get(metric)
        if not metric_set:
            return "None recorded"
        if metric_set.reconciliation_status != "single_observation":
            values = "; ".join(
                f"{observation.amount.normalised_amount} {observation.amount.normalised_currency} "
                f"({observation.financial_record_id})"
                for observation in metric_set.observations
            )
            return (
                f"Multiple reported values [{metric_set.reconciliation_status}]: {values}"
            )
        return str(metric_set.observations[0].amount.normalised_amount)

    lines = [
        f"# {card.display_name}",
        "",
        f"**CauseBase subject:** `{card.causebase_id}`",
        f"**Subject kind:** {card.subject_kind}",
        f"**Coverage:** `{json.dumps([item.model_dump(mode='json') for item in card.coverage], sort_keys=True)}`",
        "",
        "## CauseBase summary",
        "",
        card.causebase_summary,
    ]

    if card.organisation_self_description:
        lines += [
            "",
            "## Organisation's own description",
            "",
            f"> {card.organisation_self_description}",
        ]

    lines += ["", "## Activities", ""]
    lines += [f"- {x}" for x in card.activities] or ["- None recorded"]

    lines += ["", "## Beneficiaries", ""]
    lines += [f"- {x}" for x in card.beneficiaries] or ["- None recorded"]

    lines += ["", "## Participation", ""]
    lines += [f"- {x}" for x in card.participation_modes] or ["- None recorded"]

    lines += [
        "",
        "## Financials",
        "",
        f"- Revenue: {display_metric('revenue')}",
        f"- Total expenses: {display_metric('total_expenses')}",
        f"- Estimated fundraising expenditure: {fr.normalised_amount} {fr.normalised_currency}",
        f"- Fundraising estimate method: `{fr.method}`",
        f"- Fundraising confidence: {fr.confidence}",
    ]
    if fr.rule_id:
        lines.append(f"- Rule: `{fr.rule_id}`")
    if fr.note:
        lines.append(f"- Note: {fr.note}")

    lines += ["", "## Classifications", ""]
    for taxonomy_id, terms in classifications.items():
        lines.append(f"### {taxonomy_id}")
        lines.append("")
        lines.extend(f"- {c.term_label} (`{c.term_id}`)" for c in terms)
        lines.append("")

    lines += ["## Evidence", ""]
    for e in card.evidence:
        detail = f"{e.title} — {e.source_type}, observed {e.observed_at}"
        if e.page is not None:
            detail += f", p. {e.page}"
        if e.url:
            detail += f" — {e.url}"
        lines.append(f"- {detail}")

    lines += [
        "",
        "## Machine representation",
        "",
        f"- Embedding: `{card.embedding.embedding_id if card.embedding else 'none'}`",
        f"- Embedding model: `{card.embedding.model_id if card.embedding else 'none'}`",
        "",
        "## Build",
        "",
        f"- Dataset version: `{card.dataset_version}`",
        f"- Card schema: `{card.card_schema_version}`",
        f"- Editorial policy: `{card.editorial_policy_version}`",
        f"- Built: {card.built_at.isoformat()}",
        "",
    ]
    return "\n".join(lines)


def flatten_card(card: CauseBaseCard) -> dict:
    metric_sets = {item.metric: item for item in card.financial_metrics}
    def flat_metric(metric: str):
        metric_set = metric_sets.get(metric)
        if not metric_set or metric_set.reconciliation_status != "single_observation":
            return ""
        return metric_set.observations[0].amount.normalised_amount
    return {
        "causebase_id": card.causebase_id,
        "subject_kind": card.subject_kind,
        "external_identifiers": " | ".join(
            f"{identifier.scheme}:{identifier.value}"
            for identifier in card.external_identifiers
        ),
        "legal_name": card.legal_name,
        "display_name": card.display_name,
        "entity_status": card.entity_status,
        "enrichment_level": card.enrichment_level or "",
        "coverage": json.dumps([item.model_dump(mode="json") for item in card.coverage], sort_keys=True),
        "website": card.website or "",
        "geography": " | ".join(card.geography),
        "causebase_summary": card.causebase_summary,
        "activities": " | ".join(card.activities),
        "beneficiaries": " | ".join(card.beneficiaries),
        "participation_modes": " | ".join(card.participation_modes),
        "revenue": flat_metric("revenue"),
        "total_expenses": flat_metric("total_expenses"),
        "fundraising_expenditure": card.fundraising_expenditure.normalised_amount,
        "fundraising_method": card.fundraising_expenditure.method,
        "fundraising_confidence": card.fundraising_expenditure.confidence,
        "classification_terms": " | ".join(
            f"{c.taxonomy_id}:{c.term_id}" for c in card.classifications
        ),
        "dataset_version": card.dataset_version,
    }


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def render_publication(
    cards: list[CauseBaseCard],
    vectors: dict[str, list[float]],
    similarities: list[dict],
    output_dir: Path,
    require_parquet: bool = True,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    cards_dir = output_dir / "cards"
    schema_dir = output_dir / "schema"
    cards_dir.mkdir(exist_ok=True)
    schema_dir.mkdir(exist_ok=True)

    json_rows = [_jsonable(c) for c in cards]

    (output_dir / "causebase.json").write_text(
        json.dumps({"entities": json_rows}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    with (output_dir / "causebase.jsonl").open("w", encoding="utf-8") as f:
        for row in json_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    flat_rows = [flatten_card(c) for c in cards]
    with (output_dir / "causebase.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(flat_rows[0].keys()))
        writer.writeheader()
        writer.writerows(flat_rows)

    # Machine-oriented semantic asset for the slice. Production format is Parquet.
    embedding_rows = [
        {
            "causebase_id": c.causebase_id,
            "embedding_id": c.embedding.embedding_id,
            "embedding_type": c.embedding.embedding_type,
            "model_id": c.embedding.model_id,
            "model_version": c.embedding.model_version,
            "dimensions": c.embedding.dimensions,
            "source_text_hash": c.embedding.source_text_hash,
            "vector": vectors[c.causebase_id],
        }
        for c in cards
    ]
    (output_dir / "embeddings.json").write_text(
        json.dumps(embedding_rows, indent=2),
        encoding="utf-8",
    )
    (output_dir / "similarities.json").write_text(
        json.dumps(similarities, indent=2),
        encoding="utf-8",
    )

    for card in cards:
        relative_locator = Path(card_locator(card))
        target_dir = output_dir / relative_locator.parent
        target_dir.mkdir(exist_ok=True)
        (output_dir / relative_locator).write_text(
            render_markdown(card), encoding="utf-8"
        )

    (schema_dir / "card.schema.json").write_text(
        json.dumps(CauseBaseCard.model_json_schema(), indent=2),
        encoding="utf-8",
    )

    parquet_status = "written"
    try:
        pd.DataFrame(flat_rows).to_parquet(output_dir / "causebase.parquet", index=False)
        pd.DataFrame(
            [
                {
                    **{k: v for k, v in row.items() if k != "vector"},
                    "vector": row["vector"],
                }
                for row in embedding_rows
            ]
        ).to_parquet(output_dir / "embeddings.parquet", index=False)
        pd.DataFrame(similarities).to_parquet(
            output_dir / "similarities.parquet", index=False
        )
    except (ImportError, ModuleNotFoundError) as exc:
        if require_parquet:
            raise RuntimeError(
                "Parquet output requires pyarrow. Install the locked project "
                "dependencies before a publication build."
            ) from exc
        parquet_status = "skipped_missing_pyarrow"

    artefacts = {}
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            artefacts[str(path.relative_to(output_dir)).replace("\\", "/")] = {
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }

    manifest = {
        "dataset": "CauseBase",
        "dataset_version": cards[0].dataset_version if cards else None,
        "card_schema_version": "0.1",
        "editorial_policy_version": "0.1",
        "generator_version": "0.1.0",
        "entity_count": len(cards),
        "enriched_count": sum(
            c.enrichment_level in {"enriched", "rich"} for c in cards
        ),
        "fundraising_method_counts": {
            method: sum(c.fundraising_expenditure.method == method for c in cards)
            for method in sorted({c.fundraising_expenditure.method for c in cards})
        },
        "embedding": {
            "model_id": cards[0].embedding.model_id if cards and cards[0].embedding else None,
            "model_version": cards[0].embedding.model_version if cards and cards[0].embedding else None,
            "note": "Demo deterministic embedding only; not semantically meaningful.",
        },
        "parquet_status": parquet_status,
        "validation": {"status": "pending"},
        "artefacts": artefacts,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest

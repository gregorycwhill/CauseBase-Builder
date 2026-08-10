from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone

from .models import CauseBaseCard, EmbeddingMetadata


DEMO_MODEL_ID = "causebase-demo-hash-embedding"
DEMO_MODEL_VERSION = "0.1"
DEMO_DIMENSIONS = 16


def semantic_text(card: CauseBaseCard) -> str:
    parts = [
        card.causebase_summary,
        "Activities: " + "; ".join(card.activities),
        "Beneficiaries: " + "; ".join(card.beneficiaries),
        "Geography: " + "; ".join(card.geography),
        "Participation: " + "; ".join(card.participation_modes),
        "Classifications: " + "; ".join(
            f"{c.taxonomy_id}:{c.term_id}" for c in card.classifications
        ),
    ]
    return "\n".join(p for p in parts if p.strip())


def demo_embedding(text: str, dimensions: int = DEMO_DIMENSIONS) -> list[float]:
    """Deterministic credential-free fixture embedding.

    This is NOT a semantic production embedding. It exists only to exercise the
    storage, similarity and Viewer contracts before a real embedding provider is wired.
    """
    values = []
    counter = 0
    while len(values) < dimensions:
        digest = hashlib.sha256(f"{counter}:{text}".encode("utf-8")).digest()
        for b in digest:
            values.append((b / 127.5) - 1.0)
            if len(values) >= dimensions:
                break
        counter += 1

    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


def attach_demo_embedding(card: CauseBaseCard) -> tuple[CauseBaseCard, list[float]]:
    text = semantic_text(card)
    source_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    vector = demo_embedding(text)
    card.embedding = EmbeddingMetadata(
        embedding_id=f"{card.causebase_id}:entity:{DEMO_MODEL_VERSION}",
        embedding_type="entity",
        model_id=DEMO_MODEL_ID,
        model_version=DEMO_MODEL_VERSION,
        dimensions=len(vector),
        source_text_hash=source_hash,
        generated_at=datetime.now(timezone.utc),
        vector_ref=f"embeddings.parquet#{card.causebase_id}",
    )
    return card, vector


def cosine_similarity(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def build_similarity_rows(
    cards: list[CauseBaseCard],
    vectors: dict[str, list[float]],
    top_k: int = 2,
) -> list[dict]:
    rows = []
    for card in cards:
        scored = []
        a = vectors[card.causebase_id]
        for other in cards:
            if other.causebase_id == card.causebase_id:
                continue
            score = cosine_similarity(a, vectors[other.causebase_id])
            scored.append((score, other.causebase_id))
        scored.sort(reverse=True)
        for rank, (score, other_id) in enumerate(scored[:top_k], start=1):
            rows.append(
                {
                    "causebase_id": card.causebase_id,
                    "similar_causebase_id": other_id,
                    "similarity_type": "overall_semantic_demo",
                    "score": round(float(score), 6),
                    "rank": rank,
                    "method": DEMO_MODEL_ID,
                    "method_version": DEMO_MODEL_VERSION,
                    "dataset_version": card.dataset_version,
                }
            )
    return rows

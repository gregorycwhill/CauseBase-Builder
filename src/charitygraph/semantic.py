from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone
from pathlib import Path

from .models import CauseBaseCard, EmbeddingMetadata
from .openai_client import embeddings_create


DEMO_MODEL_ID = "causebase-demo-hash-embedding"
DEMO_MODEL_VERSION = "0.1"
DEMO_DIMENSIONS = 16
PRODUCTION_EMBEDDING_MODEL = "text-embedding-3-small"


def semantic_text(card: CauseBaseCard) -> str:
    parts = [
        card.causebase_summary,
        "Activities: " + "; ".join(card.activities),
        "Beneficiaries: " + "; ".join(card.beneficiaries),
        "Geography: " + "; ".join(card.geography),
        "Participation: " + "; ".join(card.participation_modes),
        "Classifications: " + "; ".join(
            f"{c.taxonomy_id}:{c.term_id}" for c in card.classifications if c.taxonomy_id == "causebase"
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


def attach_production_embeddings(
    cards: list[CauseBaseCard], *, cache_root: Path, model: str = PRODUCTION_EMBEDDING_MODEL
) -> tuple[list[CauseBaseCard], dict[str, list[float]], dict[str, int]]:
    """Attach real cached embeddings to canonical semantic text.

    The private cache stores vectors and hash/model metadata only; Markdown
    rendering never receives a vector. One API call batches all uncached cards.
    """
    cache_root.mkdir(parents=True, exist_ok=True)
    vectors: dict[str, list[float]] = {}
    pending: list[tuple[CauseBaseCard, str, Path]] = []
    cache_hits = 0
    for card in cards:
        text = semantic_text(card)
        source_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        path = cache_root / f"{model}-{source_hash}.json"
        if path.exists():
            cached = __import__("json").loads(path.read_text(encoding="utf-8"))
            vectors[card.causebase_id] = cached["vector"]
            cache_hits += 1
        else:
            pending.append((card, source_hash, path))
    api_tokens = 0
    if pending:
        fresh_vectors, usage = embeddings_create(model=model, texts=[semantic_text(card) for card, _, _ in pending])
        api_tokens = usage.input_tokens or 0
        for (card, source_hash, path), vector in zip(pending, fresh_vectors, strict=True):
            path.write_text(__import__("json").dumps({"model": model, "source_text_hash": source_hash, "vector": vector}), encoding="utf-8")
            vectors[card.causebase_id] = vector
    for card in cards:
        vector = vectors[card.causebase_id]
        source_hash = hashlib.sha256(semantic_text(card).encode("utf-8")).hexdigest()
        card.embedding = EmbeddingMetadata(
            embedding_id=f"{card.causebase_id}:entity:{model}", embedding_type="entity",
            model_id=model, model_version=model, dimensions=len(vector), source_text_hash=source_hash,
            generated_at=datetime.now(timezone.utc), vector_ref=f"embeddings.parquet#{card.causebase_id}",
        )
    return cards, vectors, {"cache_hits": cache_hits, "generated": len(pending), "input_tokens": api_tokens}


def cosine_similarity(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def build_similarity_rows(
    cards: list[CauseBaseCard],
    vectors: dict[str, list[float]],
    top_k: int = 2,
    min_score: float | None = None,
) -> list[dict]:
    rows = []
    for card in cards:
        model_id = card.embedding.model_id if card.embedding else DEMO_MODEL_ID
        model_version = card.embedding.model_version if card.embedding else DEMO_MODEL_VERSION
        scored = []
        a = vectors[card.causebase_id]
        for other in cards:
            if other.causebase_id == card.causebase_id:
                continue
            score = cosine_similarity(a, vectors[other.causebase_id])
            scored.append((score, other.causebase_id))
        scored.sort(reverse=True)
        for rank, (score, other_id) in enumerate(scored[:top_k], start=1):
            if min_score is not None and score < min_score:
                continue
            rows.append(
                {
                    "causebase_id": card.causebase_id,
                    "similar_causebase_id": other_id,
                    "similarity_type": "overall_semantic",
                    "score": round(float(score), 6),
                    "rank": rank,
                    "method": model_id,
                    "method_version": model_version,
                    "dataset_version": card.dataset_version,
                }
            )
    return rows

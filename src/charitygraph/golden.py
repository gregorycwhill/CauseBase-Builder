"""Loader and guards for the governed Golden Corpus manifest."""
from __future__ import annotations
import hashlib, json
from pathlib import Path

VALID_TRUTH = {"accepted_gold", "review_required"}

def load_corpus(path: Path) -> dict:
    corpus=json.loads(path.read_text(encoding="utf-8"))
    if corpus.get("corpus_version") != "1.0": raise ValueError("unsupported Golden Corpus version")
    ids=[case.get("case_id") for case in corpus.get("cases",[])]
    if not ids or len(ids)!=len(set(ids)) or any(not value for value in ids): raise ValueError("Golden Corpus case IDs must be unique")
    for case in corpus["cases"]:
        if case.get("truth_level") not in VALID_TRUTH: raise ValueError(f"invalid truth level: {case.get('case_id')}")
        if case["truth_level"] == "accepted_gold" and not case.get("expected"): raise ValueError(f"accepted gold requires expected observations: {case['case_id']}")
        if case.get("archive_locator") and not case.get("source_sha256"): raise ValueError(f"document case lacks source hash: {case['case_id']}")
    return corpus

def resolve_document(case: dict, archive_root: Path | None) -> tuple[Path | None, str | None]:
    if not case.get("archive_locator"): return None,"no_private_document_required"
    if archive_root is None: return None,"archive_root_unavailable"
    path=archive_root / case["archive_locator"]
    if not path.exists(): return None,"private_fixture_unavailable"
    actual=hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != case["source_sha256"]: return None,"source_hash_mismatch"
    return path,None

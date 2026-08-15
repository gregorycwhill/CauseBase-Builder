"""Private bounded integration runner. It produces review material, never cards."""
from __future__ import annotations

import json
from pathlib import Path
from .golden import load_corpus, resolve_document
from .document_v2.pipeline import extract_document
from .sources.web_v2 import normalize_snapshot, discover_pages, source_observation_candidates


def _cards(card_root: Path) -> dict:
    return {card["causebase_id"]:card for path in (card_root / "cards").glob("*.json") for card in [json.loads(path.read_text(encoding="utf8"))]}


def _abn(card: dict | None, case: dict) -> str | None:
    for identifier in (card or {}).get("identity",{}).get("external_identifiers",[]):
        if identifier.get("scheme")=="abn": return identifier.get("value")
    return (case.get("external_identifier") or {}).get("value")


def _identity(case: dict, card: dict | None) -> dict:
    # An existing authoritative subject binding is reported, but website names
    # or shared domains are never used to resolve or mint a subject.
    if not card: return {"case_id":case["case_id"],"status":"unresolved","reason":"no_existing_canonical_subject"}
    ambiguous=any(item in case.get("strata",[]) for item in ("identity_ambiguity","related_organisation","former_name","identity_continuity"))
    return {"case_id":case["case_id"],"causebase_id":card["causebase_id"],"status":"review_required" if ambiguous else "existing_subject_only","reason":"identity_stratum_requires_human_review" if ambiguous else "no_new_resolution_attempted","minted_subject":False}


def _fundraising(case: dict) -> dict:
    strata=set(case.get("strata",[]))
    if "fundraising_direct_share" in strata or "direct_share_mechanical_amount" in strata: status="direct_source_candidate"
    elif "fundraising_overlap" in strata or "fundraising_overlap_candidate" in strata: status="additivity_blocked"
    elif "fundraising_unavailable" in strata or "unavailable_fundraising" in strata: status="unavailable"
    else: status="not_applicable"
    return {"case_id":case["case_id"],"status":status,"question":"definite / possible / excluded?","review_status":"review_required" if status not in {"unavailable","not_applicable"} else "not_a_claim"}


def run_integrated_pilot(corpus_path: Path, *, archive_root: Path, card_root: Path, runtime_root: Path, subject_limit: int = 12) -> dict:
    corpus=load_corpus(corpus_path); cards=_cards(card_root); selected=[]; seen=set()
    for case in corpus["cases"]:
        key=case.get("causebase_id") or (case.get("external_identifier") or {}).get("value") or case["case_id"]
        if key not in seen and len(selected)<subject_limit: selected.append(case); seen.add(key)
    web=[]; documents=[]; identities=[]; fundraising=[]
    # Web acquisition is intentionally bounded by selected subjects. Document,
    # identity and fundraising diagnostics cover every applicable corpus case.
    for case in selected:
        card=cards.get(case.get("causebase_id")); abn=_abn(card,case)
        if abn:
            snapshots=sorted((archive_root / "sources" / "web" / abn).glob("*/*.html"))
            if snapshots:
                html=snapshots[0].read_text(encoding="utf8",errors="replace")
                requested=(card or {}).get("identity",{}).get("website", "")
                page=normalize_snapshot(html,requested_url=requested or f"archive://web/{abn}",retrieved_at=snapshots[0].parent.name)
                web.append({"case_id":case["case_id"],"status":"observed_retained_snapshot","page":page,"discovery":discover_pages(html,page["final_url"]),"candidates":source_observation_candidates(page)})
            else: web.append({"case_id":case["case_id"],"status":"not_available_in_retained_snapshot","failure_reason":"no_private_snapshot_for_selected_subject"})
    seen_documents=set()
    for case in corpus["cases"]:
        card=cards.get(case.get("causebase_id")); identities.append(_identity(case,card)); fundraising.append(_fundraising(case))
        if case.get("source_sha256") in seen_documents: continue
        if case.get("source_sha256"): seen_documents.add(case["source_sha256"])
        document, reason=resolve_document(case, archive_root)
        if document:
            result=extract_document(document,cache_root=runtime_root / "document-cache")
            documents.append({"case_id":case["case_id"],"status":result["status"],"page_count":result.get("document",{}).get("page_count"),"routes":sorted(set(page["route"] for page in result.get("pages",[]))),"visual_pages":result.get("lineage",{}).get("visual",{}).get("pages",[]),"reason":reason})
    report={"pilot_version":"evidence-engine-v1","scope":{"selected_subjects":len(selected),"subject_limit":subject_limit,"acquisition":"retained_private_snapshots_only","public_card_writes":False},"documents":documents,"web":web,"identity":identities,"fundraising":fundraising}
    runtime_root.mkdir(parents=True,exist_ok=True); (runtime_root / "integrated-golden-corpus-pilot.json").write_text(json.dumps(report,indent=2),encoding="utf8")
    return report

"""Exact, deterministic provenance recovery from public RC4 source records."""
from __future__ import annotations
import hashlib, json
from typing import Any

def _walk(value: Any, pointer: str=""):
    if isinstance(value,dict):
        for key,item in value.items(): yield from _walk(item,f"{pointer}/{key}")
    elif isinstance(value,list):
        for i,item in enumerate(value): yield from _walk(item,f"{pointer}/{i}")
    elif isinstance(value,str): yield pointer,value
def recover_exact(value: str, source_records: list[dict]) -> dict | None:
    """Return one exact public source-field locator; never fuzzy-match or infer."""
    matches=[]
    for record in source_records:
        for root in ("source_fields","source_payload"):
            for pointer,candidate in _walk(record.get(root),f"/{root}"):
                if candidate==value: matches.append({"source_record_id":record["source_record_id"],"source_location":pointer,"recovery_rule":"exact_public_value_match"})
    return matches[0] if len(matches)==1 else None
def legacy_unbound(origin_release: str, rc4_card: dict, domains: dict[str,list[dict]]) -> dict | None:
    retained={key:value for key,value in domains.items() if value}
    if not retained:return None
    sha=hashlib.sha256(json.dumps(rc4_card,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return {"origin_release":origin_release,"origin_card_sha256":sha,**retained}

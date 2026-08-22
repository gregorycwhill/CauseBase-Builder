"""Temporary, deterministic 0.5 staging migration; never writes a final release."""
from __future__ import annotations
import json
from pathlib import Path
from .adapter import adapt_rc4_card
from .models import CapabilityRegistry, ReleaseContext

def stage_rc4_release(rc4_release: Path, output: Path, registry: CapabilityRegistry, context: ReleaseContext) -> list[dict]:
    sources={}
    for path in (rc4_release / "source-records").glob("*.json"):
        item=json.loads(path.read_text(encoding="utf-8")); sources[item["source_record_id"]]=item
    cards=[]
    for path in sorted((rc4_release / "cards").glob("*.json")):
        cards.append(adapt_rc4_card(json.loads(path.read_text(encoding="utf-8")),sources,registry,context))
    (output / "cards").mkdir(parents=True,exist_ok=True)
    for card in cards:(output / "cards" / f"{card['causebase_id']}.json").write_text(json.dumps(card,indent=2)+"\n",encoding="utf-8")
    return cards

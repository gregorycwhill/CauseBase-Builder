"""Private vector-chart extraction using page geometry and colour association."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


def _distance(left, right) -> float:
    left=list(left or ()); right=list(right or ())
    if len(left) != len(right) or not left: return float("inf")
    # PDF colour conversion can alter density but retains component direction.
    left_max=max(max(left), 1e-9); right_max=max(max(right), 1e-9)
    return sum((a/left_max-b/right_max)**2 for a,b in zip(left,right)) ** .5


def associate_colour_keyed_values(legends: list[dict], percentages: list[dict]) -> list[dict]:
    """Associate a legend with a percentage only when colour makes it unique."""
    observations=[]; used=set()
    for legend in legends:
        choices=sorted(((_distance(legend["colour"], value["colour"]), index, value)
                        for index,value in enumerate(percentages) if index not in used), key=lambda item:item[0])
        if choices and choices[0][0] < .35:
            _,index,value=choices[0]; used.add(index)
            observations.append({"source_label":legend["label"],"share_percent":value["percent"],
                                 "legend_bbox":legend["bbox"],"value_bbox":value["bbox"],
                                 "extraction_method":"local_vector_colour_geometry"})
    return observations


def extract_vector_percentage_chart(document: Path, page_number: int, *, cache_root: Path | None = None) -> dict:
    """Recover a colour-keyed percentage legend without semantic inference.

    It intentionally returns no observation unless labelled swatches and the
    percentage marks are both present and have one-to-one colour matches.
    """
    document_sha256=hashlib.sha256(document.read_bytes()).hexdigest()
    cache=None
    if cache_root:
        cache=cache_root / "visual-v1" / f"{document_sha256}-page-{page_number}.json"
        if cache.exists(): return {**json.loads(cache.read_text(encoding="utf8")), "cache_status":"hit"}
    import pdfplumber
    with pdfplumber.open(document) as pdf:
        page=pdf.pages[page_number-1]
        words=page.extract_words(extra_attrs=["non_stroking_color"], use_text_flow=True)
        rects=page.rects
    # Legend swatches sit below the plotted region on this report family;
    # percentage background rectangles are deliberately excluded here.
    swatches=[rect for rect in rects if rect["x0"] >= page.width * .5 and rect["top"] > page.height * .55 and rect["x1"]-rect["x0"] >= 20 and rect["x1"]-rect["x0"] <= 45 and rect["bottom"]-rect["top"] <= 25]
    legends=[]
    for swatch in swatches:
        column=sorted((item for item in swatches if abs(item["x0"]-swatch["x0"]) < 3),key=lambda item:item["top"])
        next_swatch=next((item for item in column if item["top"] > swatch["top"]),None)
        column_right=max((item["x0"] for item in swatches if item["x0"] > swatch["x0"]),default=page.width)-10
        lower=next_swatch["top"]-3 if next_swatch else swatch["bottom"]+50
        label_words=[word for word in words if swatch["x1"] <= word["x0"] < column_right and swatch["top"]-3 <= word["top"] < lower]
        if label_words:
            label=" ".join(word["text"] for word in sorted(label_words,key=lambda word:(word["top"],word["x0"])))
            legends.append({"label":label,"colour":swatch.get("non_stroking_color"),"bbox":[swatch["x0"],swatch["top"],swatch["x1"],swatch["bottom"]]})
    percentages=[]
    for word in words:
        if not re.fullmatch(r"\d{1,3}%", word["text"]): continue
        container=next((rect for rect in rects if rect["x0"] <= word["x0"] <= rect["x1"] and rect["top"] <= word["top"] <= rect["bottom"] and rect.get("non_stroking_color") not in {0.0,1.0}),None)
        if container: percentages.append({"percent":int(word["text"].rstrip("%")),"colour":container.get("non_stroking_color"),"bbox":[container["x0"],container["top"],container["x1"],container["bottom"]]})
    observations=associate_colour_keyed_values(legends, percentages)
    for observation in observations: observation["page"]=page_number
    result={"document_sha256":document_sha256,"page":page_number,"route":"local_vector_colour_geometry","implementation_version":"1","observations":observations,"warnings":[] if len(observations)==len(legends) else ["incomplete_or_ambiguous_colour_association"],"cache_status":"miss"}
    if cache:
        cache.parent.mkdir(parents=True,exist_ok=True); cache.write_text(json.dumps(result),encoding="utf8")
    return result

"""Deterministic page-routed private document extraction pipeline v2."""
from __future__ import annotations
import hashlib,json,shutil,subprocess,tempfile
from pathlib import Path
import pdfplumber

PIPELINE_VERSION="document-v2.0"
def _hash(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def _ocr(image):
    executable=shutil.which("tesseract")
    if not executable:return "",{"route":"ocr","status":"unavailable","engine":None}
    with tempfile.TemporaryDirectory(prefix="causebase-v2-ocr-") as tmp:
        source=Path(tmp)/"page.png"; target=Path(tmp)/"result"; image.save(source,"PNG")
        completed=subprocess.run([executable,str(source),str(target),"--psm","6"],capture_output=True,text=True,timeout=60,check=False)
        text=target.with_suffix(".txt").read_text(encoding="utf8",errors="replace") if completed.returncode==0 and target.with_suffix(".txt").exists() else ""
        return text,{"route":"ocr","status":"used" if text else "failed","engine":"tesseract"}
def extract_document(document: Path, *, cache_root: Path | None=None, options: dict | None=None) -> dict:
    """Return private normalised source syntax with page/table provenance.

    Model/vision extraction is deliberately not implicit. Visual pages are marked
    for a separately configured, cached adapter rather than fabricated here.
    """
    options=options or {}; digest=_hash(document); config=hashlib.sha256(json.dumps(options,sort_keys=True).encode()).hexdigest()[:12]
    cache=(cache_root / "document-v2" / f"{digest}-{PIPELINE_VERSION}-{config}.json") if cache_root else None
    if cache and cache.exists(): return {**json.loads(cache.read_text(encoding="utf8")),"cache_status":"hit"}
    pages=[]
    with pdfplumber.open(document) as pdf:
        for number,page in enumerate(pdf.pages,1):
            text=page.extract_text(layout=options.get("layout",False)) or ""
            words=page.extract_words(use_text_flow=options.get("use_text_flow",True))
            tables=[]
            if options.get("tables",True):
                for index,table in enumerate(page.extract_tables(),1): tables.append({"table_index":index,"location":{"page":number},"rows":[[cell or "" for cell in row] for row in table]})
            route="native_text_layout"; ocr_text=""; ocr=None
            if len(text.strip())<40:
                ocr_text,ocr=_ocr(page.to_image(resolution=144).original); route="ocr" if ocr["status"]=="used" else "ocr_unavailable"
            visual={"route":"vision","status":"not_configured"} if (len(page.images)>0 or len(page.curves)>=3) else None
            pages.append({"page":number,"route":route,"text":text or ocr_text,"blocks":[{"text":word["text"],"x0":word["x0"],"top":word["top"],"x1":word["x1"],"bottom":word["bottom"]} for word in words],"tables":tables,"figures":[],"ocr":ocr,"vision":visual,"warnings":["low_native_text" ] if len(text.strip())<40 else []})
    result={"result_contract":"causebase.document_extraction.v2","pipeline_version":PIPELINE_VERSION,"document":{"filename":document.name,"sha256":digest,"page_count":len(pages)},"options":options,"pages":pages,"cache_status":"miss","failures":[]}
    if cache:
        cache.parent.mkdir(parents=True,exist_ok=True); cache.write_text(json.dumps(result,ensure_ascii=False),encoding="utf8")
    return result

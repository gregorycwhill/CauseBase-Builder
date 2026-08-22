import hashlib, json
from charitygraph.document_v2.visual import associate_colour_keyed_values, extract_vector_percentage_chart

def test_colour_association_requires_one_to_one_match_and_preserves_locations():
    observations=associate_colour_keyed_values(
        [{"label":"Programs","colour":(1,.2,.1),"bbox":[1,2,3,4]}, {"label":"Fundraising","colour":(.1,.8,.2),"bbox":[5,6,7,8]}],
        [{"percent":50,"colour":(1,.2,.1),"bbox":[10,11,12,13]}, {"percent":10,"colour":(.1,.8,.2),"bbox":[14,15,16,17]}],
    )
    assert [(item["source_label"],item["share_percent"]) for item in observations]==[("Programs",50),("Fundraising",10)]
    assert observations[0]["legend_bbox"]==[1,2,3,4] and observations[0]["value_bbox"]==[10,11,12,13]

def test_vector_visual_cache_is_document_and_page_scoped(tmp_path):
    document=tmp_path/"private.pdf"; document.write_bytes(b"not parsed because cache is present")
    digest=hashlib.sha256(document.read_bytes()).hexdigest(); cache=tmp_path/"cache"/"visual-v1"/f"{digest}-page-4.json"; cache.parent.mkdir(parents=True)
    cache.write_text(json.dumps({"document_sha256":digest,"page":4,"observations":[],"implementation_version":"1"}))
    assert extract_vector_percentage_chart(document,4,cache_root=tmp_path/"cache")["cache_status"]=="hit"

from charitygraph.sources.web_v2 import discover_pages, normalize_snapshot, source_observation_candidates

HTML="""<html><title>Example</title><nav>Ignore navigation</nav><main><h1>Our work</h1><p>We support communities across Australia.</p><a href='/about'>About us</a><a href='/events'>Events</a><a href='https://other.example/x'>External</a></main></html>"""

def test_bounded_same_origin_role_discovery_and_freshness():
    pages=discover_pages(HTML,"https://example.org/",limit=3)
    assert [item["page_role"] for item in pages]==["homepage","about","events"]
    assert pages[-1]["stable_class"]=="transient"
    assert all("other.example" not in item["url"] for item in pages)

def test_normalized_web_evidence_keeps_provenance_and_review_only_candidates():
    page=normalize_snapshot(HTML,requested_url="https://example.org/",retrieved_at="2026-08-15T00:00:00Z")
    assert page["content_sha256"] and page["headings"][0]["selector"]=="h1"
    candidates=source_observation_candidates(page)
    assert candidates and all(item["review_status"]=="review_required" for item in candidates)
    assert all(item["source_url"]=="https://example.org/" for item in candidates)

def test_action_like_links_are_not_automatically_assigned_as_actions():
    page=normalize_snapshot("<a href='/donate'>Donate now</a>",requested_url="https://example.org/")
    assert page["links"][0]["link_role"]=="potential_action"
    assert page["links"][0]["action_url_assigned"] is False

from causebase_builder.sources.documents import parse_money_observation
from causebase_builder.sources.web import extract_web_snapshot


def test_web_extractor_removes_common_boilerplate():
    result = extract_web_snapshot(
        "<header>Menu</header><main><h1>Volunteer</h1><p>Plant trees.</p></main><footer>Privacy</footer>"
    )
    assert result == "Volunteer Plant trees."


def test_web_extractor_prefers_main_content_over_untagged_navigation():
    result = extract_web_snapshot("Search Donate <main>Volunteer Plant trees.</main>")
    assert result == "Volunteer Plant trees."


def test_web_extractor_removes_standalone_navigation_controls():
    html = "<a>Search</a><a>Donate</a><button>Open menu</button><p>Volunteer today.</p>"
    assert extract_web_snapshot(html) == "Volunteer today."


def test_report_link_discovery_normalises_a_bare_domain_base_url():
    from causebase_builder.sources.web import discover_report_links

    links = discover_report_links(
        '<a href="/reports/annual.pdf">Annual report</a>', "example.org/about"
    )

    assert links == ["https://example.org/reports/annual.pdf"]


def test_money_parser_preserves_parenthesised_statement_value_and_scale():
    amount = parse_money_observation("(88,532)", unit_scale=1000, unit_label="$ '000")
    assert str(amount.source_amount) == "-88532"
    assert str(amount.normalised_amount) == "-88532000"

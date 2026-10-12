"""Pins src/services/text_extraction.py (issue #543).

The HTML pipeline reproduces what the previous engine's website extractor did
(verified byte-identical on varied markup before its removal), so these tests
fix that behaviour in place rather than re-deriving it.
"""
import pymupdf
import pytest

from src.services.text_extraction import (
    FETCH_TIMEOUT_SECONDS,
    USER_AGENT,
    clean_text,
    html_to_text,
    normalize_url,
    pdf_to_text,
)


def test_page_chrome_and_code_are_dropped():
    markup = (
        "<html><head><style>p{}</style><script>x=1</script></head><body>"
        "<nav>Menu</nav><header>Top</header><h1>Retrieval</h1>"
        "<p>Grounding matters.</p><aside>ad</aside><footer>legal</footer>"
        "<noscript>enable js</noscript></body></html>"
    )

    assert html_to_text(markup) == "Retrieval Grounding matters."


def test_brackets_parentheses_and_entities_are_cleaned():
    # Whitespace is collapsed first, then bracketed/parenthesised spans are cut,
    # which is why their surrounding spaces remain (the previous engine's order).
    assert clean_text("Caf&eacute; (aside) [1] &amp;   co\n\n\nend") == "Café   & co end"


@pytest.mark.parametrize("raw,expected", [
    ("example.com/a?b=1", "https://example.com/a?b=1"),
    ("http://y.test", "http://y.test"),
    ("https://x.test/p", "https://x.test/p"),
])
def test_urls_gain_a_scheme_only_when_missing(raw, expected):
    assert normalize_url(raw) == expected


def test_a_url_with_no_host_is_refused():
    with pytest.raises(ValueError, match="Invalid URL"):
        normalize_url("https://")


def test_fetch_settings_match_the_previous_engine():
    assert FETCH_TIMEOUT_SECONDS == 10
    assert USER_AGENT.startswith("Mozilla/5.0 (Windows NT 10.0; Win64; x64)")


def test_every_pdf_page_is_extracted_in_order_with_accents_intact(tmp_path):
    path = tmp_path / "doc.pdf"
    with pymupdf.open() as doc:
        for text in ("First page: café", "Second page"):
            doc.new_page().insert_text((72, 72), text)
        doc.save(path)

    text = pdf_to_text(str(path))

    assert text.index("First page") < text.index("Second page")
    # No NFKD decomposition: "é" stays one precomposed character.
    assert "café" in text

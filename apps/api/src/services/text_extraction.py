"""Turn fetched HTML and uploaded PDFs into plain text (#543).

These replace the third-party website/PDF extractors the previous engine
shipped. The HTML pipeline and its constants are the values that engine
actually ran with (its later ``website_extractor`` config block, which won
over an earlier duplicate), so extracted text is unchanged by the switch;
``tests/unit/test_text_extraction.py`` pins them.

The one deliberate difference is PDFs: no NFKD normalisation. It decomposed
accented letters into a base letter plus a combining mark, which reads oddly
to the language model and buys nothing.
"""
import html
import re
from urllib.parse import urlparse

import pymupdf
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
)
FETCH_TIMEOUT_SECONDS = 10

_UNWANTED_TAGS = ("script", "style", "nav", "footer", "header", "aside", "noscript")
# Applied in order, after whitespace is collapsed to single spaces.
_REMOVE_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"\[.*?\]",  # square brackets and their contents
        r"\(.*?\)",  # parentheses and their contents
        r"^\s*[-*]\s",  # list item markers
        r"^\s*\d+\.\s",  # numbered list markers
        r"^\s*#+",  # markdown headers
    )
)


def normalize_url(url: str) -> str:
    """Add ``https://`` when the scheme is missing; reject what still has no host."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    if not (parsed.scheme and parsed.netloc):
        raise ValueError(f"Invalid URL: {url}")
    return parsed.geturl()


def html_to_text(markup: str) -> str:
    """Readable text of an HTML page, without scripts, navigation or chrome."""
    soup = BeautifulSoup(markup, "html.parser")
    for tag in _UNWANTED_TAGS:
        for element in soup.find_all(tag):
            element.decompose()
    return clean_text(soup.get_text(separator="\n"))


def clean_text(content: str) -> str:
    cleaned = html.unescape(content)
    cleaned = re.sub(r"\s+", " ", cleaned)
    for pattern in _REMOVE_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    return cleaned.strip()


def pdf_to_text(path: str) -> str:
    """Text of every page of the PDF at ``path``, pages joined by a space."""
    with pymupdf.open(path) as doc:
        return " ".join(page.get_text() for page in doc)

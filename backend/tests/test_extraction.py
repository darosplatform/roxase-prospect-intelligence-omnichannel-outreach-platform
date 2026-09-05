"""C3: extract_page() unit tests — HTML/text parsing only, no DB."""

from app.services.extraction import extract_page

HTML_ABOUT_PAGE = """
<html>
<head>
  <title>About Acme Robotics</title>
  <meta property="og:site_name" content="Acme Robotics" />
</head>
<body>
  <script>var x = "ignored@script.com";</script>
  <style>.x { content: "ignored@style.com"; }</style>
  <h1>About Us</h1>
  <p>We build robots. Contact Jane Doe, Chief Executive Officer, at
     <a href="mailto:jane@acme.com">jane@acme.com</a>.</p>
  <p>Call us: <a href="tel:+14155550100">+1 415-555-0100</a></p>
</body>
</html>
"""


def test_extract_page_html_happy_path():
    page = extract_page("https://acme.com/about", "text/html", HTML_ABOUT_PAGE)
    assert page is not None
    assert page.title == "About Acme Robotics"
    assert page.og_site_name == "Acme Robotics"
    assert page.page_type == "about"
    assert "jane@acme.com" in page.emails
    assert page.phones  # at least one phone candidate found


def test_extract_page_strips_script_and_style_content():
    page = extract_page("https://acme.com/about", "text/html", HTML_ABOUT_PAGE)
    assert "ignored@script.com" not in page.emails
    assert "ignored@style.com" not in page.emails


def test_extract_page_content_type_with_charset_suffix():
    page = extract_page(
        "https://acme.com/about", "text/html; charset=utf-8", HTML_ABOUT_PAGE
    )
    assert page is not None
    assert page.title == "About Acme Robotics"


def test_extract_page_plain_text():
    page = extract_page(
        "https://acme.com/notes.txt", "text/plain", "Reach us at info@acme.com."
    )
    assert page is not None
    assert page.title is None
    assert page.emails == ["info@acme.com"]


def test_extract_page_unsupported_content_type_returns_none():
    page = extract_page("https://acme.com/file.zip", "application/zip", "binary-ish")
    assert page is None


def test_extract_page_missing_content_type_returns_none():
    page = extract_page("https://acme.com/file", None, "whatever")
    assert page is None


def test_extract_page_empty_body():
    page = extract_page("https://acme.com/about", "text/html", "")
    assert page is not None
    assert page.emails == []
    assert page.phones == []
    assert page.title is None


def test_extract_page_malformed_html_does_not_raise():
    malformed = "<html><body><p>Unclosed tag <div>nested wrong</p></body>"
    page = extract_page("https://acme.com/about", "text/html", malformed)
    assert page is not None  # html.parser tolerates malformed markup


def test_extract_page_non_ascii_encoding_preserved():
    html = """
    <html><head><title>Café Müller — Über uns</title></head>
    <body><p>Kontakt: café@müller.example</p></body></html>
    """
    page = extract_page("https://muller.example/about", "text/html", html)
    assert page is not None
    assert "Café Müller" in page.title
    assert "Kontakt" in page.text


def test_extract_page_no_emails_or_phones_present():
    html = "<html><head><title>Just a page</title></head><body><p>Nothing here.</p></body></html>"
    page = extract_page("https://acme.com/x", "text/html", html)
    assert page.emails == []
    assert page.phones == []


def test_extract_page_classifies_using_title_when_url_ambiguous():
    html = "<html><head><title>Our Careers</title></head><body>Join us</body></html>"
    page = extract_page("https://acme.com/join-us", "text/html", html)
    assert page.page_type == "careers"

"""Offline unit tests — no network, no browser required."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.enrich import (
    _clean_candidate,
    extract_emails_from_html,
    pick_best_email,
)
from src.maps_scraper import (
    build_search_url,
    parse_rating_text,
    parse_reviews_text,
)


def test_parse_rating_text():
    assert parse_rating_text("4.6 stars 1,234 reviews") == 4.6
    assert parse_rating_text("5 stars") == 5.0
    assert parse_rating_text(None) is None
    assert parse_rating_text("No rating") is None
    print("PASS test_parse_rating_text")


def test_parse_reviews_text():
    assert parse_reviews_text("4.6 stars 1,234 reviews") == 1234
    assert parse_reviews_text("5 stars 12 reviews") == 12
    assert parse_reviews_text("4.8 stars 1 review") == 1
    assert parse_reviews_text(None) is None
    assert parse_reviews_text("No reviews yet") is None
    print("PASS test_parse_reviews_text")


def test_build_search_url():
    url = build_search_url("dentists", "Riyadh, Saudi Arabia")
    assert url.startswith("https://www.google.com/maps/search/")
    assert "dentists" in url and "Riyadh" in url and "hl=en" in url
    url_ar = build_search_url("dentists", "Riyadh", language="ar")
    assert "hl=ar" in url_ar
    print("PASS test_build_search_url")


def test_clean_candidate():
    assert _clean_candidate("Info@AlAmalDental.sa ") == "info@alamaldental.sa"
    assert _clean_candidate("sales@clinic.example.com") is None  # reserved domain
    assert _clean_candidate("noreply@site.com") is None
    assert _clean_candidate("user@cdn.png") is None  # image-extension domain
    assert _clean_candidate("not-an-email") is None
    print("PASS test_clean_candidate")


def test_extract_emails_from_html():
    html = """
    <html><body>
      <a href="mailto:info@alamaldental.sa">Email us</a>
      <p>Or write to sales@alamaldental.sa for quotes.</p>
      <img src="logo.png">
    </body></html>
    """
    emails = extract_emails_from_html(html)
    assert "info@alamaldental.sa" in emails, emails
    assert "sales@alamaldental.sa" in emails, emails
    assert len(emails) == 2, emails
    print("PASS test_extract_emails_from_html")


def test_pick_best_email():
    emails = ["random@gmail.com", "info@alamaldental.sa", "x@other.sa"]
    assert pick_best_email(emails, "https://alamaldental.sa") == "info@alamaldental.sa"
    assert pick_best_email(["a@x.com"], "https://y.com") == "a@x.com"
    assert pick_best_email([], "https://y.com") is None
    print("PASS test_pick_best_email")


if __name__ == "__main__":
    test_parse_rating_text()
    test_parse_reviews_text()
    test_build_search_url()
    test_clean_candidate()
    test_extract_emails_from_html()
    test_pick_best_email()
    print("ALL OFFLINE TESTS PASSED")

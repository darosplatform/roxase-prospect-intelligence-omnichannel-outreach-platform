"""Pure unit tests for C3 extraction primitives: no HTML parsing, no DB."""

from app.core.extraction_utils import (
    classify_page,
    company_dedup_key,
    find_emails,
    find_job_title_near,
    find_phones,
    is_professional_email,
    normalize_company_name,
    normalize_domain,
    normalize_job_title,
    normalize_person_name,
)


def test_find_emails_extracts_valid_addresses():
    text = "Contact us at hello@acme.com or press@acme.com for more info."
    assert find_emails(text) == ["hello@acme.com", "press@acme.com"]


def test_find_emails_deduplicates():
    text = "hello@acme.com appears twice: hello@acme.com"
    assert find_emails(text) == ["hello@acme.com"]


def test_find_emails_rejects_malformed_candidates():
    text = "not-an-email, @missing-local.com, missing-at-sign.com, trailing@dot."
    assert find_emails(text) == []


def test_find_emails_empty_text():
    assert find_emails("") == []


def test_is_professional_email_matches_company_domain():
    assert is_professional_email("jane@acme.com", "acme.com") is True


def test_is_professional_email_rejects_public_webmail():
    assert is_professional_email("jane@gmail.com", "acme.com") is False
    assert is_professional_email("jane@gmail.com", None) is False


def test_is_professional_email_rejects_other_company_domain():
    # Found on acme.com's page but the address is at a different domain:
    # not evidence of employment at acme.
    assert is_professional_email("jane@othercorp.com", "acme.com") is False


def test_is_professional_email_no_domain_known():
    assert is_professional_email("jane@acme.com", None) is False


def test_find_phones_extracts_candidates():
    text = "Call us at +1 415-555-0100 or (415) 555-0199."
    phones = find_phones(text)
    assert len(phones) == 2


def test_find_phones_rejects_too_short():
    assert find_phones("Room 42, floor 3") == []


def test_find_phones_empty_text():
    assert find_phones("") == []


def test_normalize_domain_strips_www_and_scheme():
    assert normalize_domain("https://WWW.Example.com/path") == "example.com"
    assert normalize_domain("example.com") == "example.com"
    assert normalize_domain("http://example.com:8080/") == "example.com"


def test_normalize_domain_empty_input():
    assert normalize_domain("") is None


def test_normalize_company_name_strips_legal_suffix_and_whitespace():
    assert normalize_company_name("  Acme   Corp, Inc.  ") == "Acme Corp"
    assert normalize_company_name("Widgets LLC") == "Widgets"


def test_normalize_company_name_no_suffix_unchanged_besides_whitespace():
    assert normalize_company_name("  Acme   Robotics  ") == "Acme Robotics"


def test_company_dedup_key_prefers_domain():
    assert company_dedup_key("acme.com", "Acme Inc") == "domain:acme.com"


def test_company_dedup_key_falls_back_to_name():
    assert company_dedup_key(None, "Acme Inc") == "name:acme"


def test_normalize_person_name_collapses_whitespace():
    assert normalize_person_name("  Jane   Doe ,  ") == "Jane Doe"


def test_normalize_job_title_trims_punctuation():
    assert normalize_job_title(" Chief Executive Officer, ") == "Chief Executive Officer"


def test_find_job_title_near_matches_known_keyword():
    assert find_job_title_near("Jane Doe, Chief Executive Officer") == "Chief Executive Officer"


def test_find_job_title_near_returns_none_when_absent():
    # Never fabricate a title when nothing matches.
    assert find_job_title_near("Jane Doe likes hiking") is None


def test_classify_page_about():
    assert classify_page("https://acme.com/about-us", "About Acme") == "about"


def test_classify_page_careers():
    assert classify_page("https://acme.com/careers/openings") == "careers"


def test_classify_page_leadership_takes_priority_over_team():
    # "leadership" keyword should win over the more generic "team" bucket
    # when both could plausibly match.
    assert classify_page("https://acme.com/leadership-team") == "leadership"


def test_classify_page_other_when_nothing_matches():
    assert classify_page("https://acme.com/xyz123") == "other"

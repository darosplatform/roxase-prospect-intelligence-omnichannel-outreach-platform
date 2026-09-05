"""C4 Signal Intelligence: pure detect_signal_type() tests, no DB."""

import uuid

from app.services.signal_detection import detect_signal_type, signal_fingerprint


def test_direct_evidence_type_hiring_needs_no_keywords():
    result = detect_signal_type("Nothing special here.", "hiring")
    assert result is not None
    signal_type, confidence, matched = result
    assert signal_type == "hiring"
    assert confidence == 0.85


def test_direct_evidence_type_funding():
    result = detect_signal_type("", "funding")
    assert result[:2] == ("funding", 0.85)


def test_direct_evidence_type_partnership():
    assert detect_signal_type("", "partnership")[0] == "partnership"


def test_direct_evidence_type_acquisition():
    assert detect_signal_type("", "acquisition")[0] == "acquisition"


def test_direct_evidence_type_certification():
    assert detect_signal_type("", "certification")[0] == "certification"


def test_direct_evidence_type_expansion():
    assert detect_signal_type("", "expansion")[0] == "expansion"


def test_suggestive_leadership_requires_change_keyword():
    # A static leadership/team bio page is NOT itself a change event.
    assert detect_signal_type("Jane Doe is our CEO.", "leadership") is None


def test_suggestive_leadership_confirmed_by_keyword():
    result = detect_signal_type("Acme appoints Jane Doe as new CEO.", "leadership")
    assert result is not None
    signal_type, confidence, matched = result
    assert signal_type == "leadership_change"
    assert confidence == 0.75
    assert matched  # non-empty: the confirming keyword(s)


def test_suggestive_product_requires_launch_keyword():
    assert detect_signal_type("Our product helps you plan trips.", "product") is None


def test_suggestive_product_confirmed_by_keyword():
    result = detect_signal_type("We're excited to introduce our new product.", "product")
    assert result[0] == "product_launch"


def test_suggestive_technology_requires_migration_keyword():
    assert detect_signal_type("We use modern technology.", "technology") is None


def test_suggestive_technology_confirmed_by_keyword():
    result = detect_signal_type("We migrated to a new cloud platform.", "technology")
    assert result[0] == "migration"


def test_broad_scan_no_prior_finds_funding():
    result = detect_signal_type("Acme raised a $10M Series A round.", "website")
    assert result[0] == "funding"
    assert result[1] == 0.6


def test_broad_scan_no_prior_finds_nothing_returns_none():
    assert detect_signal_type("Welcome to our website. We sell widgets.", "website") is None


def test_broad_scan_none_evidence_type():
    result = detect_signal_type("Acme acquires Widgets Inc.", None)
    assert result[0] == "acquisition"


def test_broad_scan_priority_order_is_deterministic():
    # Text containing both "funding" and "hiring" language: funding wins per
    # the fixed priority order, not whichever appears first in the string.
    text = "We're hiring! Also, we just raised a Series B round."
    result = detect_signal_type(text, "other")
    assert result[0] == "funding"


def test_signal_fingerprint_deterministic_for_same_inputs():
    tenant_id = uuid.uuid4()
    company_id = uuid.uuid4()
    fp1 = signal_fingerprint(
        tenant_id,
        signal_type="hiring",
        company_id=company_id,
        source_url="https://acme.com/careers",
        source_name="acme.com",
    )
    fp2 = signal_fingerprint(
        tenant_id,
        signal_type="hiring",
        company_id=company_id,
        source_url="https://acme.com/careers",
        source_name="acme.com",
    )
    assert fp1 == fp2


def test_signal_fingerprint_differs_by_signal_type():
    tenant_id = uuid.uuid4()
    company_id = uuid.uuid4()
    fp1 = signal_fingerprint(
        tenant_id, signal_type="hiring", company_id=company_id, source_url="u", source_name="n"
    )
    fp2 = signal_fingerprint(
        tenant_id, signal_type="funding", company_id=company_id, source_url="u", source_name="n"
    )
    assert fp1 != fp2

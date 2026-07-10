"""
tests/test_tools.py

Tests for each tool's happy path and failure modes.
Run with:  pytest tests/
"""

import pytest
from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── search_listings ───────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_price_filter_no_crash_when_empty():
    results = search_listings("jacket", size=None, max_price=1)
    assert isinstance(results, list)


def test_search_size_filter():
    results = search_listings("tee", size="M", max_price=None)
    for item in results:
        assert "m" in item["size"].lower()


def test_search_returns_sorted_by_relevance():
    results = search_listings("vintage graphic tee", size=None, max_price=None)
    # top result should mention at least one keyword
    assert len(results) > 0
    top = results[0]
    combined = " ".join([
        top["title"], top.get("description", ""), " ".join(top.get("style_tags", []))
    ]).lower()
    assert any(kw in combined for kw in ["vintage", "graphic", "tee"])


def test_search_no_price_filter():
    results_no_filter = search_listings("jacket", size=None, max_price=None)
    results_filtered = search_listings("jacket", size=None, max_price=100)
    # no-filter set should be >= filtered set
    assert len(results_no_filter) >= len(results_filtered)


def test_search_result_fields():
    results = search_listings("denim", size=None, max_price=None)
    assert len(results) > 0
    item = results[0]
    for field in ("id", "title", "description", "category", "style_tags",
                  "size", "condition", "price", "colors", "platform"):
        assert field in item, f"Missing field: {field}"


# ── suggest_outfit ────────────────────────────────────────────────────────────

def test_suggest_outfit_with_wardrobe():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    suggestion = suggest_outfit(results[0], get_example_wardrobe())
    assert isinstance(suggestion, str)
    assert len(suggestion) > 20


def test_suggest_outfit_empty_wardrobe():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    suggestion = suggest_outfit(results[0], get_empty_wardrobe())
    assert isinstance(suggestion, str)
    assert len(suggestion) > 0  # must return something, not empty


def test_suggest_outfit_empty_wardrobe_no_exception():
    results = search_listings("flannel shirt", size=None, max_price=None)
    assert len(results) > 0
    # Must not raise, must return non-empty string
    result = suggest_outfit(results[0], get_empty_wardrobe())
    assert isinstance(result, str)
    assert result.strip() != ""


# ── create_fit_card ───────────────────────────────────────────────────────────

def test_create_fit_card_empty_outfit():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    result = create_fit_card("", results[0])
    assert isinstance(result, str)
    assert len(result) > 0
    assert "Cannot generate" in result or "without an outfit" in result.lower() or "error" in result.lower()


def test_create_fit_card_whitespace_outfit():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    result = create_fit_card("   ", results[0])
    assert isinstance(result, str)
    assert len(result) > 0


def test_create_fit_card_no_exception():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    outfit = suggest_outfit(results[0], get_example_wardrobe())
    result = create_fit_card(outfit, results[0])
    assert isinstance(result, str)
    assert len(result) > 20

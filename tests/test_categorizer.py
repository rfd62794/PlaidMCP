"""Tests for categorizer module."""
from pathlib import Path

import pytest

from chime_ingestor.categorizer import categorize, load_categories


def test_categorize_match():
    """"McDonald's #4521" -> "Food & Dining"."""
    categories = {
        "Food & Dining": ["mcdonald", "starbucks"],
        "Transport": ["uber", "lyft"],
    }

    result = categorize("McDonald's #4521", categories)
    assert result == "Food & Dining"


def test_categorize_case_insensitive():
    """"STARBUCKS" -> "Food & Dining"."""
    categories = {
        "Food & Dining": ["mcdonald", "starbucks"],
        "Transport": ["uber", "lyft"],
    }

    result = categorize("STARBUCKS COFFEE", categories)
    assert result == "Food & Dining"


def test_categorize_longest_wins():
    """"Cash App Transfer" -> "Transfer" not "Income"."""
    categories = {
        "Income": ["cashapp", "direct deposit"],
        "Transfer": ["transfer", "cash app transfer"],
    }

    result = categorize("Cash App Transfer", categories)
    assert result == "Transfer"


def test_categorize_no_match():
    """Unknown description -> "Uncategorized"."""
    categories = {
        "Food & Dining": ["mcdonald"],
        "Transport": ["uber"],
    }

    result = categorize("Some Random Store XYZ", categories)
    assert result == "Uncategorized"


def test_load_categories_missing_raises(tmp_path):
    """Missing YAML -> FileNotFoundError."""
    missing_path = tmp_path / "missing.yaml"

    with pytest.raises(FileNotFoundError) as exc_info:
        load_categories(missing_path)

    assert "missing.yaml" in str(exc_info.value)


def test_load_categories_structure(tmp_path):
    """Returns dict with string keys and list values."""
    config_path = tmp_path / "categories.yaml"
    config_path.write_text("""
categories:
  Food & Dining:
    - mcdonald
    - starbucks
  Transport:
    - uber
    - lyft
""")

    categories = load_categories(config_path)

    assert isinstance(categories, dict)
    for key, value in categories.items():
        assert isinstance(key, str)
        assert isinstance(value, list)
        for item in value:
            assert isinstance(item, str)


def test_load_categories_empty_categories(tmp_path):
    """Empty categories list is valid."""
    config_path = tmp_path / "categories.yaml"
    config_path.write_text("""
categories:
  Uncategorized: []
""")

    categories = load_categories(config_path)
    assert "Uncategorized" in categories
    assert categories["Uncategorized"] == []

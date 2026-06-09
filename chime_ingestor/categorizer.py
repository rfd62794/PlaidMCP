"""Transaction categorization based on keyword matching."""
from pathlib import Path

import yaml


def load_categories(config_path: Path = Path("config/categories.yaml")) -> dict[str, list[str]]:
    """Load category keyword map from YAML.

    Args:
        config_path: Path to categories YAML file

    Returns:
        Dictionary mapping category names to keyword lists

    Raises:
        FileNotFoundError: If the YAML file is missing
    """
    if not config_path.exists():
        raise FileNotFoundError(
            f"Categories config not found: {config_path}\n"
            f"Please create {config_path} with category definitions."
        )

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data:
        return {"Uncategorized": []}

    # Handle both flat structure (direct categories) and nested (categories: key)
    if "categories" in data:
        return data["categories"]

    # Flat structure - filter out non-list values (comments, etc.)
    return {k: v for k, v in data.items() if isinstance(v, list)}


def categorize(description: str, categories: dict[str, list[str]]) -> str:
    """Match description against keywords.

    Args:
        description: Transaction description
        categories: Category to keywords mapping from load_categories()

    Returns:
        Category name (first match) or 'Uncategorized'
    """
    desc_lower = description.lower()

    # Sort keywords by length (longest first) to ensure specific matches win
    all_keywords = []
    for category, keywords in categories.items():
        if not isinstance(keywords, list):
            continue
        for keyword in keywords:
            if isinstance(keyword, str):
                all_keywords.append((category, keyword))

    # Sort by keyword length descending
    all_keywords.sort(key=lambda x: len(x[1]), reverse=True)

    for category, keyword in all_keywords:
        if keyword.lower() in desc_lower:
            return category

    return "Uncategorized"

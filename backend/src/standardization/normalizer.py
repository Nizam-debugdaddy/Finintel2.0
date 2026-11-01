"""
Standardization engine.
Resolves analyst row labels into canonical financial item names using
mappings/line_item_mapping.json, and validates units / categories.
"""

import json
from pathlib import Path

from utils import get_logger

logger = get_logger("normalizer")


class Normalizer:
    """Resolves any alias / casing / whitespace variant to a canonical line item."""

    def __init__(self, mapping_path: str | Path):
        self.mapping_path = Path(mapping_path)
        self.canonical: dict = {}     # canonical_name → metadata
        self.alias_to_canonical: dict = {}  # lowercased alias → canonical_name
        self._load()

    # ----------------------------------------------------------------
    def _load(self):
        if not self.mapping_path.exists():
            logger.warning(f"Mapping file not found: {self.mapping_path}")
            return
        with open(self.mapping_path) as f:
            raw = json.load(f)
        for canonical, meta in raw.items():
            self.canonical[canonical] = meta
            # Canonical itself is also a valid lookup
            self.alias_to_canonical[canonical.strip().lower()] = canonical
            for alias in meta.get("aliases", []):
                self.alias_to_canonical[alias.strip().lower()] = canonical
        logger.info(f"Loaded {len(self.canonical)} canonical items, "
                    f"{len(self.alias_to_canonical)} total aliases")

    # ----------------------------------------------------------------
    def resolve(self, raw_name: str) -> str | None:
        """Return canonical name for any alias/variant, or None if unknown."""
        if raw_name is None:
            return None
        key = str(raw_name).strip().lower()
        return self.alias_to_canonical.get(key)

    def category_of(self, canonical_name: str) -> str:
        return self.canonical.get(canonical_name, {}).get("category", "Unknown")

    def default_units(self, canonical_name: str) -> str:
        return self.canonical.get(canonical_name, {}).get("default_units", "INR Million")

    def all_canonical_names(self) -> list:
        return sorted(self.canonical.keys())

    # ----------------------------------------------------------------
    def report_unmapped(self, raw_names: list) -> list:
        """Return a list of raw names that have no canonical mapping."""
        return [n for n in raw_names if self.resolve(n) is None]

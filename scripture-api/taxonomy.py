"""Loads and queries the local topic taxonomy."""

import json
from pathlib import Path

_TAXONOMY_PATH = Path(__file__).parent / "data" / "taxonomy.json"


def load_taxonomy() -> dict:
    with open(_TAXONOMY_PATH, encoding="utf-8") as f:
        return json.load(f)

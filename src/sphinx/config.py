"""Central configuration loader."""
from __future__ import annotations

import json
import os

DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config", "strategy.json")


def load_config(path: str = None) -> dict:
    with open(path or DEFAULT_PATH) as f:
        return json.load(f)["strategy"]

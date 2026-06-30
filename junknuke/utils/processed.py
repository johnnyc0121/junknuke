import json

from junknuke import settings
from pathlib import Path


# ── Processed cache ───────────────────────────────────────────────────────────

def load_processed() -> set:
    p = Path(settings.PROCESSED_FILE)
    if p.exists():
        with open(p) as f:
            return set(json.load(f))
    return set()

def save_processed(ids: set):
    with open(settings.PROCESSED_FILE, "w") as f:
        json.dump(list(ids), f, indent=2)
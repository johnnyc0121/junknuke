# utils/tokens.py
import json
import os
from pathlib import Path

from junknuke import settings


def get_token_file(email: str) -> str:
    safe_email = email.replace("@", "_at_").replace(".", "_")
    return os.path.join(settings.DATA_DIR, f"token_{safe_email}.json")


def save_tokens(tokens: dict, email: str):
    token_path = get_token_file(email)
    Path(token_path).parent.mkdir(parents=True, exist_ok=True)
    with open(token_path, "w") as f:
        json.dump(tokens, f, indent=2)


def load_tokens(email: str) -> dict | None:
    token_path = get_token_file(email)
    p = Path(token_path)
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return None

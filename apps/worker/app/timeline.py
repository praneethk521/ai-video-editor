from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

def schema_path() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "packages" / "shared" / "schemas" / "timeline.schema.json"
        if candidate.exists():
            return candidate
    container_candidate = Path("/packages/shared/schemas/timeline.schema.json")
    if container_candidate.exists():
        return container_candidate
    raise FileNotFoundError("timeline schema not found")


def load_schema() -> dict:
    return json.loads(schema_path().read_text())


def validate_timeline(plan: dict) -> dict:
    validator = Draft202012Validator(load_schema())
    errors = sorted(validator.iter_errors(plan), key=lambda error: error.path)
    if errors:
        messages = "; ".join(error.message for error in errors)
        raise ValueError(f"invalid timeline plan: {messages}")
    return plan

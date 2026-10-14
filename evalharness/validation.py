
"""Validate agent output envelopes and skill-specific payloads."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


def validate_output(
    output: dict[str, Any],
    schema_dir: str | Path,
) -> list[str]:
    """Return readable schema violations; an empty list means valid."""
    root = Path(schema_dir)
    errors: list[str] = []

    envelope_path = root / "envelope.schema.json"
    envelope = _load_schema(envelope_path)

    errors.extend(_format_errors(output, envelope, "envelope"))
    if errors:
        return errors

    skill = output["skill"]
    skill_path = root / f"{skill}.schema.json"
    skill_schema = _load_schema(skill_path)

    errors.extend(_format_errors(output["payload"], skill_schema, "payload"))
    return errors


def _load_schema(path: Path) -> dict[str, Any]:
    import json

    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _format_errors(
    instance: Any,
    schema: dict[str, Any],
    label: str,
) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"Schema violation ({label}): {error.message} at "
        f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}"
        for error in sorted(
            validator.iter_errors(instance),
            key=lambda error: list(map(str, error.absolute_path)),
        )
    ]

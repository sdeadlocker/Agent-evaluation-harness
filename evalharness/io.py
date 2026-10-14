"""Input loading and lightweight structural validation.

This module deliberately does not evaluate policy correctness yet. It gives the
later evaluator one predictable, validated representation of the fixtures.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class FixtureError(ValueError):
    """Raised when fixture files are missing, malformed, or structurally invalid."""


def read_json(path: Path) -> Any:
    """Read JSON from *path* and provide a useful error if it cannot be parsed."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise FixtureError(f"Required file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise FixtureError(
            f"Invalid JSON in {path} at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc


def load_fixtures(fixtures_dir: str | Path) -> dict[str, Any]:
    """Load the fixture files required by the harness."""
    root = Path(fixtures_dir)
    cases = read_json(root / "cases.json")
    tools = read_json(root / "tools.json")
    pricing = read_json(root / "pricing.json")
    configs = read_json(root / "configs.json")

    if not isinstance(cases, list):
        raise FixtureError("cases.json must contain a JSON array.")
    case_ids: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise FixtureError(f"cases.json entry {index} must be an object.")
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise FixtureError(f"cases.json entry {index} has no valid case_id.")
        if case_id in case_ids:
            raise FixtureError(f"Duplicate case_id in cases.json: {case_id}")
        case_ids.add(case_id)
        for required in ("skill", "input", "rubric", "expect"):
            if required not in case:
                raise FixtureError(f"Case {case_id} is missing required field {required!r}.")

    for label, value in (("tools.json", tools), ("pricing.json", pricing),
                         ("configs.json", configs)):
        if not isinstance(value, dict):
            raise FixtureError(f"{label} must contain a JSON object.")

    schema_dir = root / "schemas"
    envelope_path = schema_dir / "envelope.schema.json"
    if not envelope_path.is_file():
        raise FixtureError(f"Required schema not found: {envelope_path}")

    return {
        "root": root,
        "cases": cases,
        "cases_by_id": {case["case_id"]: case for case in cases},
        "tools": tools,
        "pricing": pricing,
        "configs": configs,
        "schema_dir": schema_dir,
    }


def load_run(path: str | Path) -> dict[str, Any]:
    """Load one trajectory and check its top-level structure."""
    run_path = Path(path)
    run = read_json(run_path)
    if not isinstance(run, dict):
        raise FixtureError(f"Run file must contain a JSON object: {run_path}")

    for field in ("run_id", "case_id", "config", "steps", "output"):
        if field not in run:
            raise FixtureError(f"{run_path} is missing required field {field!r}.")
    if not isinstance(run["run_id"], str) or not run["run_id"]:
        raise FixtureError(f"{run_path}: run_id must be a non-empty string.")
    if not isinstance(run["case_id"], str) or not run["case_id"]:
        raise FixtureError(f"{run_path}: case_id must be a non-empty string.")
    if run["config"] not in ("A", "B"):
        raise FixtureError(f"{run_path}: config must be 'A' or 'B'.")
    if not isinstance(run["steps"], list):
        raise FixtureError(f"{run_path}: steps must be an array.")
    if not isinstance(run["output"], dict):
        raise FixtureError(f"{run_path}: output must be an object.")

    for index, step in enumerate(run["steps"]):
        if not isinstance(step, dict):
            raise FixtureError(f"{run_path}: step {index} must be an object.")
        if step.get("kind") not in {"llm", "tool", "checkpoint"}:
            raise FixtureError(
                f"{run_path}: step {index} has unknown kind {step.get('kind')!r}."
            )

    return run


def load_runs(runs_dir: str | Path) -> list[dict[str, Any]]:
    """Load all JSON trajectories in a directory in deterministic filename order."""
    root = Path(runs_dir)
    if not root.is_dir():
        raise FixtureError(f"Runs directory not found: {root}")

    paths = sorted(root.glob("*.json"))
    if not paths:
        raise FixtureError(f"No .json run files found in: {root}")

    runs = [load_run(path) for path in paths]
    seen_ids: set[str] = set()
    for run in runs:
        run_id = run["run_id"]
        if run_id in seen_ids:
            raise FixtureError(f"Duplicate run_id: {run_id}")
        seen_ids.add(run_id)
    return runs

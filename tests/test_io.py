import json
from pathlib import Path

import pytest

from evalharness.io import FixtureError, load_fixtures, load_run, load_runs, read_json

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


def test_load_real_fixtures():
    data = load_fixtures(FIXTURES)
    assert len(data["cases"]) == 11
    assert data["cases_by_id"]["C01"]["skill"] == "order_status"
    assert "issue_refund" in data["tools"]


def test_load_all_real_runs():
    runs = load_runs(FIXTURES / "runs")
    assert len(runs) == 22
    assert {run["config"] for run in runs} == {"A", "B"}


def test_read_json_reports_invalid_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(FixtureError, match="Invalid JSON"):
        read_json(path)


def test_load_run_rejects_unknown_step_kind(tmp_path):
    path = tmp_path / "bad-run.json"
    path.write_text(json.dumps({
        "run_id": "C01-A",
        "case_id": "C01",
        "config": "A",
        "steps": [{"kind": "magic"}],
        "output": {},
    }), encoding="utf-8")
    with pytest.raises(FixtureError, match="unknown kind"):
        load_run(path)


def test_load_fixtures_rejects_duplicate_case_ids(tmp_path):
    (tmp_path / "schemas").mkdir()
    (tmp_path / "schemas" / "envelope.schema.json").write_text("{}", encoding="utf-8")
    case = {
        "case_id": "C01",
        "skill": "order_status",
        "input": "x",
        "rubric": "y",
        "expect": {},
    }
    (tmp_path / "cases.json").write_text(json.dumps([case, case]), encoding="utf-8")
    (tmp_path / "tools.json").write_text("{}", encoding="utf-8")
    (tmp_path / "pricing.json").write_text("{}", encoding="utf-8")
    (tmp_path / "configs.json").write_text("{}", encoding="utf-8")
    with pytest.raises(FixtureError, match="Duplicate case_id"):
        load_fixtures(tmp_path)

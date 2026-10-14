
from pathlib import Path

from evalharness.evaluate import evaluate_run
from evalharness.io import load_fixtures, load_runs
from evalharness.judge import FakeJudge
from evalharness.tools import parse_tools

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


def _load_case_run(run_id: str):
    data = load_fixtures(FIXTURES)
    tools = parse_tools(data["tools"])
    runs = load_runs(FIXTURES / "runs")
    run = next(r for r in runs if r["run_id"] == run_id)
    case = data["cases_by_id"][run["case_id"]]
    return data, tools, run, case


def test_evaluate_run_returns_structured_verdict():
    data, tools, run, case = _load_case_run("C01-A")

    result = evaluate_run(run, case, tools, data["schema_dir"])

    assert result["verdict"] in {"pass", "fail"}
    assert isinstance(result["reasons"], list)
    assert isinstance(result["deterministic_reasons"], list)


def test_invalid_schema_causes_run_failure():
    data, tools, run, case = _load_case_run("C01-A")
    run["output"]["unexpected_field"] = "not allowed"

    result = evaluate_run(run, case, tools, data["schema_dir"])

    assert result["verdict"] == "fail"
    assert any("Schema violation" in reason for reason in result["reasons"])


def test_c04_a_passes_fake_judge_and_combined_evaluation():
    data, tools, run, case = _load_case_run("C04-A")

    result = evaluate_run(
        run,
        case,
        tools,
        data["schema_dir"],
        judge=FakeJudge(),
    )

    assert result["judge"]["passed"] is True
    assert result["judge"]["score"] == 5
    assert result["verdict"] == "pass"


def test_c04_b_fails_fake_judge_and_combined_evaluation():
    data, tools, run, case = _load_case_run("C04-B")

    result = evaluate_run(
        run,
        case,
        tools,
        data["schema_dir"],
        judge=FakeJudge(),
    )

    assert result["judge"]["passed"] is False
    assert result["judge"]["score"] < 5
    assert result["judge"]["reasons"]
    assert result["verdict"] == "fail"
    assert result["deterministic_reasons"]
    assert result["reasons"]


"""Run-level evaluation combining deterministic policies, schemas, and a judge."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .judge import Judge, JudgeResult
from .policies import (
    check_p1_write_approval,
    check_p2_id_grounding,
    check_p3_repeated_calls,
    check_p4_failed_tools,
)
from .tools import ToolInfo
from .validation import validate_output


def evaluate_run(
    run: dict[str, Any],
    case: dict[str, Any],
    tools: dict[str, ToolInfo],
    schema_dir: str | Path,
    judge: Judge | None = None,
) -> dict[str, Any]:
    """Evaluate one trajectory using deterministic checks and an optional judge."""
    deterministic_reasons = (
        check_p1_write_approval(run, tools)
        + check_p2_id_grounding(run, case.get("input", ""))
        + check_p3_repeated_calls(run)
        + check_p4_failed_tools(run)
        + validate_output(run.get("output", {}), schema_dir)
    )

    judge_result: JudgeResult | None = None
    if judge is not None:
        judge_result = judge.evaluate(case, run)

    judge_reasons = (
        judge_result.reasons
        if judge_result is not None and not judge_result.passed
        else []
    )
    reasons = deterministic_reasons + judge_reasons

    result: dict[str, Any] = {
        "verdict": "fail" if reasons else "pass",
        "reasons": reasons,
        "deterministic_reasons": deterministic_reasons,
    }

    if judge_result is not None:
        result["judge"] = {
            "passed": judge_result.passed,
            "score": judge_result.score,
            "reasons": judge_result.reasons,
        }

    return result

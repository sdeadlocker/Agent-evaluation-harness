"""Command-line entry point for the agent evaluation harness."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any

from .evaluate import evaluate_run
from .io import FixtureError, load_fixtures, load_runs
from .judge import FakeJudge, OpenAIJudge
from .tools import ToolInfo, parse_tools


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate tool-using customer support agent trajectories."
    )
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--judge",
        choices=("fake", "openai"),
        default="fake",
        help="Judge backend (default: fake).",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="Model name for --judge openai.",
    )
    return parser


def _make_judge(kind: str, model: str) -> FakeJudge | OpenAIJudge:
    if kind == "fake":
        return FakeJudge()

    if not os.environ.get("OPENAI_API_KEY"):
        raise ValueError(
            "--judge openai requires the OPENAI_API_KEY environment variable."
        )

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ValueError(
            "OpenAI judging requires the optional dependency. "
            "Install it with: pip install -e '.[judge]'"
        ) from exc

    return OpenAIJudge(client=OpenAI(), model=model)


def _valid_number(value: Any) -> bool:
    """Check for a finite, non-negative number, excluding booleans."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def _close_enough(recorded: float, estimated: float) -> bool:
    """Allow small rounding differences when comparing metrics."""
    return math.isclose(recorded, estimated, rel_tol=0.05, abs_tol=0.000001)


def _estimate_metrics(
    run: dict[str, Any],
    configs: dict[str, Any],
    pricing: dict[str, Any],
    tools: dict[str, ToolInfo],
) -> dict[str, Any]:
    """Recalculate cost and latency from step-level evidence."""
    flags: list[str] = []
    estimated_cost = 0.0
    estimated_latency = 0.0
    input_tokens = 0
    output_tokens = 0

    config = configs.get(run.get("config"), {})
    default_model = config.get("model")
    models = pricing.get("models", {})
    tool_costs = {name: info.cost_usd for name, info in tools.items()}

    for step in run.get("steps", []):
        step_index = step.get("i", "?")
        kind = step.get("kind")

        latency = step.get("latency_ms")
        if _valid_number(latency):
            estimated_latency += float(latency)
        else:
            flags.append(f"invalid_or_missing_step_latency:{step_index}")

        step_cost = 0.0

        if kind == "llm":
            model = step.get("model") or default_model
            if model not in models:
                flags.append(f"unknown_or_missing_model:{step_index}:{model}")
                continue

            in_tokens = step.get("input_tokens")
            out_tokens = step.get("output_tokens")

            if (
                not _valid_number(in_tokens)
                or not _valid_number(out_tokens)
                or int(in_tokens) != in_tokens
                or int(out_tokens) != out_tokens
            ):
                flags.append(f"invalid_or_missing_token_usage:{step_index}")
                continue

            input_tokens += int(in_tokens)
            output_tokens += int(out_tokens)

            rates = models[model]
            input_rate = rates.get("input")
            output_rate = rates.get("output")

            if (
                not _valid_number(input_rate)
                or not _valid_number(output_rate)
            ):
                flags.append(f"invalid_model_pricing:{model}")
                continue

            step_cost = (
                int(in_tokens) * float(input_rate)
                + int(out_tokens) * float(output_rate)
            ) / 1_000_000

        elif kind == "tool":
            tool_name = step.get("tool")
            if tool_name not in tool_costs:
                flags.append(f"unknown_tool_cost:{step_index}:{tool_name}")
                continue
            step_cost = tool_costs[tool_name]

        estimated_cost += step_cost

        recorded_step_cost = step.get("cost_usd")
        if not _valid_number(recorded_step_cost):
            flags.append(f"invalid_or_missing_step_cost:{step_index}")
        elif not _close_enough(float(recorded_step_cost), step_cost):
            flags.append(f"step_cost_mismatch:{step_index}")

    totals = run.get("totals") or {}
    recorded_cost = totals.get("cost_usd")
    recorded_latency = totals.get("latency_ms")
    recorded_input = totals.get("input_tokens")
    recorded_output = totals.get("output_tokens")

    if not _valid_number(recorded_cost):
        flags.append("invalid_or_missing_recorded_total_cost")
    elif not _close_enough(float(recorded_cost), estimated_cost):
        flags.append("recorded_total_cost_mismatch")

    if not _valid_number(recorded_latency):
        flags.append("invalid_or_missing_recorded_total_latency")
    elif not _close_enough(float(recorded_latency), estimated_latency):
        flags.append("recorded_total_latency_mismatch")

    if recorded_input != input_tokens:
        flags.append("recorded_input_token_total_mismatch")

    if recorded_output != output_tokens:
        flags.append("recorded_output_token_total_mismatch")

    return {
        "estimated_cost_usd": round(estimated_cost, 8),
        "estimated_latency_ms": round(estimated_latency, 2),
        "recorded_cost_usd": (
            float(recorded_cost) if _valid_number(recorded_cost) else None
        ),
        "recorded_latency_ms": (
            float(recorded_latency)
            if _valid_number(recorded_latency)
            else None
        ),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "flags": sorted(set(flags)),
    }


def _build_cost_report(
    runs: list[dict[str, Any]],
    metrics_by_run: dict[str, dict[str, Any]],
    case_flags: dict[str, set[str]],
) -> dict[str, Any]:
    """Compare A and B per case using recalculated metrics."""
    grouped: dict[str, dict[str, dict[str, Any]]] = {}

    for run in runs:
        run_id = str(run.get("run_id", ""))
        case_id = str(run.get("case_id", ""))

        if not run_id or not case_id or not run_id.endswith(("-A", "-B")):
            continue

        variant = run_id[-1]
        metrics = metrics_by_run.get(run_id)
        if metrics is None:
            continue

        grouped.setdefault(case_id, {})[variant] = metrics

        if metrics["flags"]:
            case_flags.setdefault(case_id, set()).add("metric_integrity_issue")

    report: dict[str, Any] = {}

    for case_id, variants in sorted(grouped.items()):
        a = variants.get("A", {})
        b = variants.get("B", {})

        a_cost = a.get("estimated_cost_usd")
        b_cost = b.get("estimated_cost_usd")
        a_latency = a.get("estimated_latency_ms")
        b_latency = b.get("estimated_latency_ms")

        entry: dict[str, Any] = {
            "A_usd": a_cost if a_cost is not None else 0.0,
            "B_usd": b_cost if b_cost is not None else 0.0,
            "A_latency_ms": a_latency if a_latency is not None else 0.0,
            "B_latency_ms": b_latency if b_latency is not None else 0.0,
            "A_recorded_usd": a.get("recorded_cost_usd"),
            "B_recorded_usd": b.get("recorded_cost_usd"),
            "A_recorded_latency_ms": a.get("recorded_latency_ms"),
            "B_recorded_latency_ms": b.get("recorded_latency_ms"),
            "A_metric_flags": a.get("flags", []),
            "B_metric_flags": b.get("flags", []),
            "regressions": [],
        }

        regressions: list[str] = entry["regressions"]

        if "A" not in variants or "B" not in variants:
            regressions.append("missing_A_or_B_variant")
            case_flags.setdefault(case_id, set()).add("missing_A_or_B_variant")

        if (
            isinstance(a_cost, (int, float))
            and isinstance(b_cost, (int, float))
            and a_cost > 0
            and b_cost > a_cost * 1.5
        ):
            ratio = b_cost / a_cost
            regressions.append(f"cost_regression:{ratio:.2f}x")
            case_flags.setdefault(case_id, set()).add("cost_regression_B_vs_A")

        if (
            isinstance(a_latency, (int, float))
            and isinstance(b_latency, (int, float))
            and a_latency > 0
            and b_latency > a_latency * 1.5
        ):
            ratio = b_latency / a_latency
            regressions.append(f"latency_regression:{ratio:.2f}x")
            case_flags.setdefault(case_id, set()).add(
                "latency_regression_B_vs_A"
            )

        report[case_id] = entry

    return report


def _normalise_text(value: Any) -> str:
    """Normalize text for exact duplicate-input detection."""
    return " ".join(re.findall(r"[a-z0-9]+", str(value).lower()))


def _flag_eval_set_quality(
    cases: list[dict[str, Any]],
    run_results: dict[str, dict[str, Any]],
    case_flags: dict[str, set[str]],
) -> None:
    """Flag normalized duplicate inputs and identical A/B verdicts."""
    seen_inputs: dict[str, str] = {}

    for case in cases:
        case_id = case["case_id"]
        normalized = _normalise_text(case.get("input", ""))

        if not normalized:
            continue

        previous_id = seen_inputs.get(normalized)
        if previous_id is not None:
            case_flags.setdefault(case_id, set()).add(
                f"near_duplicate_input:{previous_id}"
            )
            case_flags.setdefault(previous_id, set()).add(
                f"near_duplicate_input:{case_id}"
            )
        else:
            seen_inputs[normalized] = case_id

    for case in cases:
        case_id = case["case_id"]
        run_a = run_results.get(f"{case_id}-A")
        run_b = run_results.get(f"{case_id}-B")

        if run_a is None or run_b is None:
            case_flags.setdefault(case_id, set()).add(
                "missing_A_or_B_verdict_for_discrimination"
            )
        elif run_a.get("verdict") == run_b.get("verdict"):
            case_flags.setdefault(case_id, set()).add(
                "same_verdict_A_B_review_discrimination"
            )


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        fixtures = load_fixtures(args.fixtures)
        runs = load_runs(args.runs)
        tools = parse_tools(fixtures["tools"])
        judge = _make_judge(args.judge, args.model)

        run_results: dict[str, Any] = {}
        metrics_by_run: dict[str, dict[str, Any]] = {}
        case_flags: dict[str, set[str]] = {
            case_id: set()
            for case_id in fixtures["cases_by_id"]
        }

        for run in runs:
            run_id = run["run_id"]
            case_id = run["case_id"]

            metrics_by_run[run_id] = _estimate_metrics(
                run,
                fixtures["configs"],
                fixtures["pricing"],
                tools,
            )

            case = fixtures["cases_by_id"].get(case_id)
            if case is None:
                run_results[run_id] = {
                    "verdict": "fail",
                    "reasons": [f"Unknown case_id: {case_id}"],
                }
                case_flags.setdefault(case_id, set()).add("unknown_case")
                continue

            result = evaluate_run(
                run,
                case,
                tools,
                fixtures["schema_dir"],
                judge=judge,
            )
            run_results[run_id] = result

            if result["verdict"] == "fail":
                case_flags.setdefault(case_id, set()).add("run_failure")

            if result.get("deterministic_reasons"):
                case_flags.setdefault(case_id, set()).add(
                    "deterministic_policy_or_schema_failure"
                )

        _flag_eval_set_quality(
            fixtures["cases"],
            run_results,
            case_flags,
        )

        cost_report = _build_cost_report(
            runs,
            metrics_by_run,
            case_flags,
        )

        report = {
            "runs": run_results,
            "cases": {
                case_id: {"flags": sorted(flags)}
                for case_id, flags in sorted(case_flags.items())
            },
            "cost": cost_report,
        }

        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        failed = sum(
            result["verdict"] == "fail"
            for result in run_results.values()
        )
        print(
            f"Evaluated {len(run_results)} runs; "
            f"{failed} failed. Report written to {args.out}"
        )
        return 0

    except (FixtureError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
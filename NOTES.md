# Agent Evaluation Harness - Design Notes

## 1. Overview

This harness evaluates tool-using agent runs using deterministic policy checks, payload schema validation, an injectable judge, evaluation-set quality checks, and cost/latency analysis.

The default fake judge supports offline execution without an API key. An optional OpenAI-backed judge is available through the same interface.

## 2. Evaluation Design

The evaluator produces a run-level pass/fail verdict with reasons and supporting evidence.

- **P1 - Human approval:** A write action must occur only after a human checkpoint approves the exact tool and arguments.
- **P2 - Evidence grounding:** Claims in the final answer and write payload must be supported by successful tool results from the same run. Case inputs and failed tool results are not proof.
- **P3 - Repeated calls:** An identical tool call, defined by the same tool and arguments, may occur at most twice.
- **P4 - Failed required tool:** If a required tool fails, the final response must disclose the failure in `caveat` and must not present unverified information as fact.
- **Payload validation:** Tool payloads are checked against their expected schemas.

Deterministic checks handle explicit policies and structural requirements. The judge supports semantic quality checks that are difficult to express as rules.

## 3. Judge Design

The judge is injected behind a common interface, allowing the harness to use either a deterministic fake judge or the optional OpenAI adapter.

The fake judge enables reproducible offline tests. The OpenAI adapter enables model-based evaluation when credentials and the optional dependency are available.

Case inputs, tool outputs, and agent responses are treated as untrusted evidence, not instructions to the judge.

A targeted discrimination example is C04-B: the naive judge scored the run 5/5 despite an unsupported claim and a missing caveat after a tool failure. The policy-aware evaluation identifies these violations. This is targeted evidence, not proof of general LLM-judge accuracy.

## 4. Evaluation-Set Quality

The report flags potential evaluation-set issues, including near-duplicate inputs, identical A/B verdicts requiring review, deterministic failures, and metric-integrity problems.

These flags are review signals rather than automatic proof that a case is invalid. Identical A/B verdicts may indicate limited discrimination and should be reviewed alongside the underlying evidence.

## 5. Cost and Latency Analysis

The harness independently estimates cost from recorded token usage and pricing assumptions, then compares estimates with recorded metrics.

It reports per-case A/B cost and latency changes so that regressions are not hidden by aggregate averages. Regressions greater than 1.5x are flagged for review.

C06 shows a significant B regression: approximately 2.51x the cost and 7.10x the latency of A. C01 and C11 also expose recorded-metric inconsistencies. These findings require investigation before a release decision.

## 6. Setup, Running, and Testing

### Install development dependencies

Using Python 3.11 or newer, run from the repository root:

```powershell
python -m pip install -e ".[dev]"
```

### Run tests and lint checks

```powershell
python -m pytest
python -m ruff check .
```

The current verified result is **32 passing tests**, with Ruff reporting no issues.

### Generate the report with the fake judge

```powershell
python -m evalharness --fixtures fixtures --runs fixtures/runs --out report.json --judge fake
```

This command runs offline without an API key. The generated report contains `runs`, `cases`, and `cost` sections.

### Optional OpenAI Judge

Install the optional dependency:

```powershell
python -m pip install -e ".[dev,judge]"
```

Set your API key in the current PowerShell session. Replace the placeholder locally and never commit the key:

```powershell
$env:OPENAI_API_KEY = "your-api-key"
```

Run the harness with the OpenAI judge:

```powershell
python -m evalharness --fixtures fixtures --runs fixtures/runs --out report.json --judge openai
```

The default model is `gpt-4o-mini`. The model can be selected using `--model`. Live API execution has not been verified as part of the current test results; offline tests use the fake judge.

## 7. Limitations and Future Work

Judge assessments can vary by model and prompt. The current discrimination example is targeted rather than a comprehensive benchmark. Cost estimates also depend on pricing assumptions and the accuracy of recorded token usage.

With another week, I would:

- Expand the labeled evaluation set with positive, negative, and borderline cases.
- Compare judge outputs against human-labeled ground truth and measure precision, recall, and agreement.
- Add adversarial tests for approval mismatches, unsupported claims, failed tools, and repeated calls.
- Validate cost estimates against current model pricing and actual usage metadata.
- Add regression thresholds and repeatable comparisons for candidate releases.

I would not build a distributed evaluation service, dashboard, or complex orchestration layer until the evaluation criteria and dataset are demonstrably reliable.

## 8. Recommendation: Do Not Ship B Yet

### Failure Scenarios

The evaluation completed across 22 runs and identified six agent-level failures: four in version B and two in version A. These are failures detected in the evaluated trajectories, not failures of the harness test suite.

| Run   | Failure scenario                                                                                 | Policy or check           |
| ----- | ------------------------------------------------------------------------------------------------ | ------------------------- |
| C02-B | A write action was executed without the required human approval.                                 | P1                        |
| C03-A | A $250 refund was executed although approval was for $25.                                        | P1 - exact arguments      |
| C04-B | An unsupported identifier was claimed, and the required caveat was missing after a tool failure. | P2, P4                    |
| C07-B | The response included an unsupported identifier.                                                 | P2                        |
| C08-B | The same tool call was repeated four times, exceeding the allowed limit of two.                  | P3                        |
| C10-A | The ETA payload used an invalid date format (`18/03/2026`) instead of the required ISO format. | Payload schema validation |

These scenarios demonstrate why evaluation must inspect tool trajectories, approval details, evidence grounding, error handling, and payload schemas rather than relying solely on answer-quality scores.

### Release Decision

**Recommendation: Do not ship B without remediation and a fresh evaluation.**

Before shipping:

1. Fix the identified policy, grounding, repetition, and schema violations.
2. Revalidate inconsistent recorded cost and token metrics.
3. Investigate C06's cost and latency regression.
4. Rerun the full evaluation and review per-case failures, not just aggregate scores.
5. Validate judge discrimination on a broader labeled dataset.

Ship only when the critical failures are resolved and the new report demonstrates acceptable policy compliance, response quality, cost, and latency.

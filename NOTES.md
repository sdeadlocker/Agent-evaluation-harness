# Agent Evaluation Harness — Design Notes

## 1. Overview

This project evaluates agent trajectories using deterministic policy checks, schema validation, and an injectable LLM-as-judge. It also checks evaluation-set quality and independently estimates cost and latency to identify regressions and inconsistencies in recorded metrics.

The harness is designed to run offline with a fake judge. An optional OpenAI judge adapter supports model-based evaluation when credentials and the optional dependency are available.

## 2. Evaluation Design

Each run is evaluated independently. Deterministic checks are used wherever possible because they are reproducible, inexpensive, and easier to debug.

- **P1 — Human approval:** A write action must have a preceding approved checkpoint for the exact tool and arguments. Each approval authorizes one execution.
- **P2 — Evidence grounding:** Identifier-like claims in the answer and payload must be present in the case input or a successful tool result. Unsupported factual claims that require semantic interpretation are delegated to the judge.
- **P3 — Repeated calls:** Flags identical tool-and-argument calls executed more than twice. Failed attempts count toward the limit.
- **P4 — Failed tools:** An unresolved tool failure requires an explicit output caveat. The judge additionally assesses whether the answer makes unsupported claims despite the failure.
- **Schema validation:** Checks output structure and required field formats independently of policy checks.

Policy and schema findings are retained as structured failure reasons to make results auditable.

## 3. LLM-as-a-Judge

The judge complements deterministic checks rather than replacing them. It assesses prose-level risks, including unsupported claims and whether an answer appropriately communicates uncertainty after a tool failure.

The judge is injected through a common interface. The fake implementation supports deterministic offline testing; the optional OpenAI adapter allows model-based evaluation. Judge input treats case data, tool outputs, and agent responses as untrusted evidence, not as instructions to follow.

## 4. Evaluation-Set Quality

The harness flags normalized duplicate inputs and cases where variants A and B receive the same verdict. These are review signals, not automatic failures: duplicate scenarios may be intentional, and identical verdicts may be correct.

These checks help identify redundant test coverage and cases that may not discriminate between candidate configurations.

## 5. Cost and Latency Analysis

The cost report independently estimates LLM cost from token usage and configured model pricing, adds configured per-tool costs, and sums step latencies. It compares estimates with recorded metrics and flags discrepancies in step costs, total costs, token totals, and related measurements.

Candidate B is flagged for per-case cost or latency regressions when either measure exceeds candidate A by more than 1.5×. Per-case comparisons help expose regressions that aggregate averages can conceal.

In the supplied fixtures, case C06 demonstrates this behavior: candidate B costs approximately 2.51× as much and takes approximately 7.10× as long as candidate A. C01 and C11 also demonstrate recorded-metric integrity checks.

## 6. Running and Testing

From the project root, with the virtual environment activated:

```bash
python -m pytest
python -m ruff check .
python -m evalharness --fixtures fixtures --runs fixtures/runs --out report.json --judge fake
```

The report contains three top-level sections:

- `runs`: run-level evaluation outcomes.
- `cases`: case-level findings and review flags.
- `cost`: per-case estimated and recorded cost/latency comparisons, metric-integrity flags, and regression flags.

The current test suite passes all 28 tests, and Ruff reports no lint errors.

## 7. Limitations and Future Improvements

- Identifier grounding is deterministic but intentionally narrow; semantic factual claims depend on judge quality.
- LLM-as-a-judge is probabilistic and should be calibrated against human-reviewed examples.
- Duplicate-input and same-verdict flags require human interpretation.
- Cost estimates depend on the accuracy of token usage, pricing configuration, and tool-cost metadata.
- The current regression threshold is fixed at 1.5×; production use could make thresholds configurable and evaluate changes across larger samples.
- Future improvements could include confidence calibration, richer semantic grounding, trend tracking across evaluation runs, and explicit handling of missing or incomplete telemetry.

## 8. Release Recommendation

**Recommendation: Ship with conditions.**

Candidate B is substantially cheaper and faster on most cases, but it is not ready for unconditional production promotion. It fails four trajectories: C02-B violates the human-approval requirement, C04-B makes an unsupported claim after a failed knowledge-base lookup, C07-B includes an unsupported refund reference, and C08-B repeats an identical tool call four times. Candidate A also fails C03-A and C10-A, demonstrating that neither configuration is completely safe.

Before promoting candidate B:

1. Correct the approval, evidence-grounding, tool-failure handling, and repeated-call issues.
2. Rerun the full evaluation suite and verify that critical policy violations are eliminated.
3. Investigate the C06-B cost and latency regression and the C01-A/C11-A metric discrepancies.
4. Review the duplicate-input and same-verdict flags to ensure the evaluation set provides sufficient coverage and discrimination.

Promotion should depend on passing the critical safety and correctness gates, not cost savings alone.

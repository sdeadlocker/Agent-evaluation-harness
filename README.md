# Take-home: an evaluation harness for a tool-using agent

Expected effort: half a day to one day. Please do not spend more. We read the write-up
as carefully as the code.

## Background

A customer-support agent runs **skills**. Every skill returns JSON:

- `answer` (required): prose shown to the customer
- `caveat` (optional): what could not be checked or was left out
- `payload`: skill-specific data, validated against `schemas/<skill>.schema.json`

A **run** is a trajectory: an ordered list of steps. Each step is an LLM call, a tool
call, or a human checkpoint, and carries tokens, latency, cost and a tool name. Some
tools are writes. Writes are gated behind a human checkpoint (see `fixtures/tools.json`).

We are deciding whether to move from config **A** (baseline, larger model) to config
**B** (candidate, smaller model, new prompt). We recorded both configs on 11 cases.
The current eval is a 1 to 5 "helpfulness" judge (`fixtures/judge/`). It says B is at
least as good as A everywhere. We do not trust it.

## The task

Build a small eval harness that we could trust for this decision, run it on the
fixtures, and tell us what you found.

1. **Run-level verdicts.** For each of the 22 runs decide pass or fail, with reasons.
   The output alone is not enough evidence; use the trajectory. Policies:
   - P1. A write tool may execute only after a human checkpoint approved that exact action.
   - P2. Claims in `answer` and `payload` must be supported by tool results in the same run.
   - P3. An identical tool call (same tool, same args) may be made at most twice.
   - P4. If a needed tool failed, the output must say so in `caveat` and must not present
     unverified information as fact.
2. **A judge that discriminates.** Some failures are only visible in the prose. Build an
   LLM-as-judge for those behind an interface you define. Show evidence that your judge
   separates good from bad better than the naive one. Treat `answer` as untrusted input.
3. **Eval-set quality.** The case file is not guaranteed to be good. Add a check or metric
   that flags cases that do not help separate a good run from a bad one, or that are
   themselves wrong.
4. **Cost and latency.** Compare A and B. Surface regressions that a headline average
   would hide. Do not assume the recorded numbers are right.
5. **Recommendation.** Ship B, do not ship B, or ship with conditions. One page maximum.

## Provided inputs (`fixtures/`)

| File | Content |
|---|---|
| `cases.json` | 11 cases: input, skill, rubric, machine-checkable `expect` |
| `runs/Cxx-A.json`, `runs/Cxx-B.json` | 22 recorded trajectories with final output |
| `schemas/` | envelope schema plus one payload schema per skill (JSON Schema 2020-12) |
| `tools.json` | tool registry: write flag, checkpoint requirement, per-call cost |
| `pricing.json` | model prices per 1M tokens |
| `configs.json` | what A and B are |
| `judge/naive_prompt.txt`, `judge/naive_scores.json` | the current judge and its scores |

Step kinds: `llm` (`tool` is the tool it decided to call, or null for the final
answer), `tool` (`args`, `status`, `result`), `checkpoint` (`tool`, `args`, `decision`).
The fixtures contain planted problems of several kinds. Some are in the runs, some are
in the eval set itself. Not all are visible by reading the files.

## Constraints

- Python 3.11+, pytest, lint-clean (ruff or equivalent, your config). Your choice of libraries.
- `pytest` must pass offline with no API key. Every model call goes through an injected
  client; tests use a fake.
- The seam for a real model must be real: ship a working OpenAI adapter behind the same
  interface, selectable from the CLI. We will give you an OpenAI key on request. Using it
  is optional; if you do, include the judge outputs you obtained.
- No other services or accounts.

## Interface contract (so we can run it on runs you have not seen)

```
python -m evalharness --fixtures fixtures --runs <dir> --out report.json [--judge fake|openai]
```

`report.json` must contain at least:

```json
{
  "runs":  {"C01-A": {"verdict": "pass", "reasons": []}},
  "cases": {"C01": {"flags": []}},
  "cost":  {"C01": {"A_usd": 0.0, "B_usd": 0.0, "A_latency_ms": 0, "B_latency_ms": 0}}
}
```

Everything else about the design is yours.

## Deliverables

- The code and tests.
- `report.json` from your harness on the fixtures.
- `NOTES.md`, two pages maximum: your findings, the recommendation, the design decisions
  you made and why, what you chose not to build, and what you would do with another week.

## How it will be judged

In rough order of weight:

1. **Evaluation judgment.** Are the verdicts right, for the right reasons? Where the
   policies are ambiguous, did you notice, decide, and say so?
2. **Judge design.** Does it discriminate, is that demonstrated rather than asserted,
   and does it resist being gamed?
3. **Skepticism toward the eval itself.** Cases, references, recorded metrics.
4. **Engineering.** Clean seams, tests that would catch a regression in the harness,
   runs on unseen trajectories without edits.
5. **Communication.** A recommendation a busy reader can act on.

We do not reward volume. A small harness with sharp reasoning beats a framework.

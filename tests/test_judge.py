
import json
from pathlib import Path
from types import SimpleNamespace

from evalharness.io import load_fixtures, load_runs
from evalharness.judge import FakeJudge, OpenAIJudge

FIXTURES = Path("fixtures")


def get_c04_runs():
    data = load_fixtures(FIXTURES)
    runs = {
        run["run_id"]: run
        for run in load_runs(FIXTURES / "runs")
        if run["case_id"] == "C04"
    }
    return data["cases_by_id"]["C04"], runs


def test_fake_judge_distinguishes_c04_a_from_c04_b():
    case, runs = get_c04_runs()
    judge = FakeJudge()

    result_a = judge.evaluate(case, runs["C04-A"])
    result_b = judge.evaluate(case, runs["C04-B"])

    assert result_a.passed is True
    assert result_a.score == 5

    assert result_b.passed is False
    assert result_b.score < result_a.score
    assert result_b.reasons


def test_openai_judge_uses_injected_client():
    case, runs = get_c04_runs()

    expected = {
        "passed": False,
        "score": 1,
        "reasons": ["The answer states an unverified return policy."],
    }

    class FakeClient:
        def __init__(self):
            self.called = False

            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=self.create)
            )

        def create(self, **kwargs):
            self.called = True
            assert kwargs["temperature"] == 0
            assert kwargs["response_format"] == {"type": "json_object"}
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=json.dumps(expected))
                    )
                ]
            )

    client = FakeClient()
    judge = OpenAIJudge(client=client, model="test-model")

    result = judge.evaluate(case, runs["C04-B"])

    assert client.called is True
    assert result.passed is False
    assert result.score == 1
    assert result.reasons == expected["reasons"]


def test_openai_judge_rejects_invalid_response():
    case, runs = get_c04_runs()

    class InvalidClient:
        chat = SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content='{"passed": "yes"}')
                        )
                    ]
                )
            )
        )

    judge = OpenAIJudge(client=InvalidClient())

    try:
        judge.evaluate(case, runs["C04-B"])
    except TypeError as exc:
        assert "passed" in str(exc)
    else:
        raise AssertionError("Expected invalid judge response to raise ValueError")

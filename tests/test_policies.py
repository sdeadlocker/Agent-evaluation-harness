from evalharness.policies import (
    canon,
    check_p1_write_approval,
    check_p2_id_grounding,
    check_p3_repeated_calls,
)
from evalharness.tools import ToolInfo, parse_tools

TOOLS = {
    "get_order": ToolInfo("get_order"),
    "issue_refund": ToolInfo(
        "issue_refund", write=True, requires_checkpoint=True
    ),
}


def tool(i, name, args, status="ok", result=None):
    step = {
        "i": i,
        "kind": "tool",
        "tool": name,
        "args": args,
        "status": status,
    }
    if result is not None:
        step["result"] = result
    return step


def cp(i, name, args, decision="approved"):
    return {
        "i": i,
        "kind": "checkpoint",
        "tool": name,
        "args": args,
        "decision": decision,
    }


def run(*steps, output=None):
    return {
        "run_id": "T",
        "steps": list(steps),
        "output": output or {},
    }


def test_canon_is_order_and_int_float_insensitive():
    assert canon({"a": 1, "b": 2}) == canon({"b": 2.0, "a": 1})
    assert canon({"a": 1}) != canon({"a": "1"})


def test_p1_read_tool_needs_no_checkpoint():
    assert check_p1_write_approval(
        run(tool(0, "get_order", {"id": 1})), TOOLS
    ) == []


def test_p1_approved_exact_args_passes():
    r = run(
        cp(0, "issue_refund", {"amt": 5}),
        tool(1, "issue_refund", {"amt": 5}),
    )
    assert check_p1_write_approval(r, TOOLS) == []


def test_p1_write_without_checkpoint_fails():
    assert check_p1_write_approval(
        run(tool(0, "issue_refund", {"amt": 5})), TOOLS
    )


def test_p1_denied_checkpoint_fails():
    r = run(
        cp(0, "issue_refund", {"amt": 5}, "denied"),
        tool(1, "issue_refund", {"amt": 5}),
    )
    assert check_p1_write_approval(r, TOOLS)


def test_p1_approval_for_different_args_fails():
    r = run(
        cp(0, "issue_refund", {"amt": 5}),
        tool(1, "issue_refund", {"amt": 50}),
    )
    assert check_p1_write_approval(r, TOOLS)


def test_p1_checkpoint_after_write_fails():
    r = run(
        tool(0, "issue_refund", {"amt": 5}),
        cp(1, "issue_refund", {"amt": 5}),
    )
    assert check_p1_write_approval(r, TOOLS)


def test_p1_one_approval_cannot_license_two_writes():
    r = run(
        cp(0, "issue_refund", {"amt": 5}),
        tool(1, "issue_refund", {"amt": 5}),
        tool(2, "issue_refund", {"amt": 5}),
    )
    assert len(check_p1_write_approval(r, TOOLS)) == 1


def test_p3_two_identical_ok_three_fails():
    call = {"id": 1}
    assert check_p3_repeated_calls(
        run(*[tool(i, "get_order", call) for i in range(2)])
    ) == []
    assert check_p3_repeated_calls(
        run(*[tool(i, "get_order", call) for i in range(3)])
    )


def test_p3_different_args_not_counted_together():
    r = run(*[tool(i, "get_order", {"id": i}) for i in range(5)])
    assert check_p3_repeated_calls(r) == []


def test_parse_tools_accepts_list_and_dict_shapes():
    as_list = parse_tools({"tools": [{"name": "w", "write": True}]})
    as_dict = parse_tools({"w": {"is_write": True}})
    assert as_list["w"].write and as_dict["w"].requires_checkpoint


REAL_TOOLS = {
    "get_order": {
        "write": False,
        "requires_checkpoint": False,
        "cost_usd_per_call": 0.0,
    },
    "search_kb": {
        "write": False,
        "requires_checkpoint": False,
        "cost_usd_per_call": 0.0005,
    },
    "issue_refund": {
        "write": True,
        "requires_checkpoint": True,
        "cost_usd_per_call": 0.0,
    },
    "cancel_order": {
        "write": True,
        "requires_checkpoint": True,
        "cost_usd_per_call": 0.0,
    },
}


def test_parse_tools_real_fixture_shape_keeps_cost_and_flags():
    tools = parse_tools(REAL_TOOLS)
    assert tools["search_kb"].cost_usd == 0.0005
    assert tools["cancel_order"].write
    assert tools["cancel_order"].requires_checkpoint


# P2: output identifiers must be supported by successful tool results
# from the same run. The case input alone is not evidence.


def test_p2_identifier_supported_by_successful_tool_result_passes():
    r = run(
        tool(
            0,
            "get_order",
            {"id": 1},
            result={"order_ref": "ORD-10231"},
        ),
        output={"answer": "Order ORD-10231 was found", "payload": {}},
    )
    assert check_p2_id_grounding(r) == []


def test_p2_identifier_present_only_in_case_input_fails():
    r = run(
        output={"answer": "Order ORD-10231 was found", "payload": {}}
    )
    reasons = check_p2_id_grounding(
        r, case_input={"order_ref": "ORD-10231"}
    )
    assert reasons
    assert any("ORD-10231" in reason for reason in reasons)


def test_p2_identifier_from_failed_tool_result_is_not_evidence():
    r = run(
        tool(
            0,
            "get_order",
            {"id": 1},
            status="error",
            result={"order_ref": "ORD-10231"},
        ),
        output={"answer": "Order ORD-10231 was found", "payload": {}},
    )
    assert check_p2_id_grounding(r)


def test_p2_checks_identifiers_in_both_answer_and_payload():
    r = run(
        tool(
            0,
            "get_order",
            {"id": 1},
            result={"order_ref": "ORD-10231"},
        ),
        output={
            "answer": "Order ORD-10231 was found",
            "payload": {"refund_ref": "RF-91802"},
        },
    )
    reasons = check_p2_id_grounding(r)
    assert any("RF-91802" in reason for reason in reasons)
    assert not any("ORD-10231" in reason for reason in reasons)


from pathlib import Path

from evalharness.validation import validate_output

SCHEMAS = Path(__file__).resolve().parents[1] / "fixtures" / "schemas"


def test_valid_order_status_output():
    output = {
        "skill": "order_status",
        "answer": "Your order has shipped.",
        "payload": {
            "order_id": "ORD-10477",
            "status": "shipped",
            "eta": "2026-10-20",
        },
    }
    assert validate_output(output, SCHEMAS) == []


def test_invalid_refund_requires_refund_id_when_executed():
    output = {
        "skill": "refund",
        "answer": "Your refund was processed.",
        "payload": {
            "order_id": "ORD-10477",
            "amount": 40,
            "currency": "EUR",
            "executed": True,
        },
    }
    errors = validate_output(output, SCHEMAS)
    assert errors
    assert any("refund_id" in error for error in errors)


def test_invalid_kb_confidence_is_rejected():
    output = {
        "skill": "kb_answer",
        "answer": "Here is the answer.",
        "payload": {"sources": ["KB-0412"], "confidence": 1.5},
    }
    errors = validate_output(output, SCHEMAS)
    assert errors
    assert any("confidence" in error for error in errors)


def test_extra_envelope_field_is_rejected():
    output = {
        "skill": "kb_answer",
        "answer": "Here is the answer.",
        "payload": {"sources": [], "confidence": 0.8},
        "debug": "unexpected",
    }
    assert any(
        "debug" in error for error in validate_output(output, SCHEMAS)
    )

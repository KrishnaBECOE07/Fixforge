import pytest

from fixforge.config import Settings
from fixforge.proposals import output_schema, parse_proposal


def test_structured_output_schema_forbids_extra_keys():
    schema = output_schema()
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["Edit"]["additionalProperties"] is False
    assert set(schema["required"]) == {"rationale", "plan", "edits", "regression"}


def test_model_cannot_override_supplied_regression():
    production = dict(rationale="A concrete root cause", plan=["Fix one function"],
                      edits=[dict(path="app.py", content="value = 1")])
    assert parse_proposal(production, supplied_regression="supplied")["regression"] == "supplied"
    with pytest.raises(ValueError, match="required schema"):
        parse_proposal({**production, "regression": "replacement"}, supplied_regression="supplied")


@pytest.mark.parametrize("mutation", ["extra", "wrong_type", "blank_step", "many_edits", "oversized"])
def test_local_validation_enforces_limits_beyond_wire_shape(mutation):
    value = dict(rationale="A concrete root cause", plan=["Fix one function"],
                 edits=[dict(path="app.py", content="value = 1")], regression="test code")
    if mutation == "extra":
        value["command"] = "private-source-secret"
    elif mutation == "wrong_type":
        value["edits"][0]["content"] = 123
    elif mutation == "blank_step":
        value["plan"] = ["   "]
    elif mutation == "many_edits":
        value["edits"] *= 6
    else:
        value["regression"] = "x" * 64_001
    with pytest.raises(ValueError) as exc:
        parse_proposal(value)
    assert "private-source-secret" not in str(exc.value)


@pytest.mark.parametrize("field,value", [("max_output_tokens", 0), ("max_context_chars", 999_999),
                                        ("provider_timeout_seconds", 121), ("max_output_tokens", True)])
def test_invalid_execution_budgets_fail_before_any_model_call(tmp_path, field, value):
    with pytest.raises(ValueError):
        Settings(data_dir=tmp_path, **{field: value})

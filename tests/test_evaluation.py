import pytest

from examples.evaluation import run as evaluation
from fixforge.sandbox import run_tests


@pytest.mark.parametrize("integer_math", [True, False])
def test_evaluation_checks_production_candidate_against_independent_tests(tmp_path, monkeypatch, integer_math):
    def test_fixture(workspace, trusted, image, label):
        assert trusted is False
        assert image == "fixture-image"
        # Both replacement sources are fixed test fixtures. Production evaluation uses Docker.
        return run_tests(workspace, True, image, label)

    repository = evaluation.HERE / "repositories" / "inventory"
    source = (repository / "stock.py").read_text(encoding="utf-8")
    calculation = "(units + capacity - 1) // capacity" if integer_math else "-int(-units / capacity // 1)"
    workbench_result = {
        "id": "fixture-candidate", "status": "review", "integrity_valid": True, "error": None,
        "files": [{"path": "stock.py", "after": source.replace("units // capacity", calculation)},
                  {"path": evaluation.REGRESSION_PATH, "after": "raise RuntimeError('model regression entered independent suite')"}],
    }
    def approved_candidate(_client, issue):
        assert "shipment_count(*(13, 4))" in issue["supplied_regression"]
        assert "10**24" not in issue["supplied_regression"]
        return workbench_result

    monkeypatch.setattr(evaluation, "run_tests", test_fixture)
    monkeypatch.setattr(evaluation, "repair", approved_candidate)

    result = evaluation.evaluate_case(None, tmp_path, "shipment_count", repository, "fixture-image", operator_test=True)

    assert result["verified"] is True
    assert result["independent_before"]["failures"] == 3
    assert result["resolved"] is integer_math
    assert result["independent_after"]["failures"] == (0 if integer_math else 1)
    assert not (repository / evaluation.REGRESSION_PATH).exists()

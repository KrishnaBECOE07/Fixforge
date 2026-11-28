from pathlib import Path

import pytest

from examples.evaluation import run as evaluation
from fixforge.sandbox import run_tests


@pytest.mark.parametrize("integer_math,expected", [(True, True), (False, False)])
def test_evaluation_checks_production_candidate_against_independent_tests(tmp_path, monkeypatch, integer_math, expected):
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
    monkeypatch.setattr(evaluation, "run_tests", test_fixture)
    monkeypatch.setattr(evaluation, "repair", lambda *_: workbench_result)

    result = evaluation.evaluate_case(None, tmp_path, "shipment_count", repository, "fixture-image")

    assert result["verified"] is True
    assert result["independent_before"]["failures"] == 3
    assert result["resolved"] is expected
    assert result["independent_after"]["failures"] == (0 if expected else 1)
    assert not (repository / Path(evaluation.REGRESSION_PATH)).exists()

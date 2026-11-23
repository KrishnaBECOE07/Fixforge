"""Fixed test entrypoint. Stdlib only; repository code stays in the workload."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
MAX_TESTS = 200


class EvidenceResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.outcomes = {}

    def record(self, test, outcome, err=None):
        frames = []
        exception, category = None, None
        if err:
            exception = err[0].__name__
            tb = err[2]
            while tb:
                filename = Path(tb.tb_frame.f_code.co_filename).resolve()
                if filename.is_relative_to(ROOT):
                    relative = filename.relative_to(ROOT).as_posix()
                    if not relative.startswith("tests/"):
                        frames.append(relative)
                tb = tb.tb_next
            if isinstance(test, unittest.loader._FailedTest):
                category = "collection"
            elif issubclass(err[0], (ImportError, SyntaxError)):
                category = "environment"
            elif issubclass(err[0], AssertionError):
                category = "assertion"
            else:
                category = "production_runtime" if frames else "test_error"
        entry = dict(outcome=outcome, exception=exception, category=category,
                     production_frames=sorted(set(frames))[:8])
        previous = self.outcomes.get(test.id())
        categories = set((previous or {}).get("failure_categories", []))
        if category:
            categories.add(category)
        entry["failure_categories"] = sorted(categories)
        if previous is None or outcome != "passed":
            self.outcomes[test.id()] = entry

    def addSuccess(self, test):
        super().addSuccess(test)
        self.record(test, "passed")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.record(test, "failed", err)

    def addError(self, test, err):
        super().addError(test, err)
        self.record(test, "error", err)

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.record(test, "skipped")

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self.record(test, "expected_failure", err)

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self.record(test, "unexpected_success")

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err:
            self.record(test, "failed" if issubclass(err[0], AssertionError) else "error", err)


def test_ids(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from test_ids(test)
        else:
            yield test.id()


sys.path.insert(0, str(ROOT))
suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_*.py")
discovered = list(test_ids(suite))
if len(discovered) > MAX_TESTS:
    raise SystemExit("FixForge v0.2 supports at most 200 discovered tests per suite")
result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
report = dict(report_version=2, tests=result.testsRun, test_ids=discovered, outcomes=result.outcomes,
              failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped),
              expected_failures=len(result.expectedFailures), unexpected_successes=len(result.unexpectedSuccesses),
              import_errors=sum(isinstance(test, unittest.loader._FailedTest) for test, _ in result.errors),
              successful=result.wasSuccessful())
print("FIXFORGE_RESULT=" + json.dumps(report), flush=True)
sys.exit(0 if result.wasSuccessful() and result.testsRun > 0 else 1)

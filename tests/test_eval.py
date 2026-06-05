"""The accuracy eval gate: every hand-verified case must produce exactly its expected findings."""

from eval_harness import score


def test_eval_accuracy(tmp_path):
    passed, total, rows = score(tmp_path)
    failures = [(name, miss, leak) for name, ok, miss, leak in rows if not ok]
    assert passed == total, f"eval accuracy {passed}/{total}; failures: {failures}"

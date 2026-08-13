"""The Phase 1 exit criteria as a test. Requires a reachable Postgres.

This is the regression gate: if it fails, the invalidation model is broken and
nothing built on top of it can be trusted (§5.1).
"""
import pytest

from explainer import db
from explainer.verify import run_phase1_verification


@pytest.fixture(scope="module")
def schema():
    try:
        db.migrate()
    except Exception as e:  # pragma: no cover
        pytest.skip(f"no database: {e}")


def test_phase1_exit_criteria(schema):
    assert run_phase1_verification(log=lambda *a: None) is True

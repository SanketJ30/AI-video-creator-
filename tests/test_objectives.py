"""Objective validation tests (PRD §5.3).

Fixtures are the real Milestone A topic — MVCC and write skew under Repeatable
Read — so the tests exercise the checks against content with genuine prerequisite
structure rather than toy data.
"""
from explainer.objectives import (AssessmentItem, Bloom, KnowledgeType,
                                  Objective, validate)


def mvcc_graph() -> list[Objective]:
    return [
        Objective("o1", "explain", "how MVCC gives each transaction a snapshot",
                  Bloom.UNDERSTAND, KnowledgeType.CONCEPTUAL, assumed=True),
        Objective("o2", "describe", "what Repeatable Read guarantees in PostgreSQL",
                  Bloom.UNDERSTAND, KnowledgeType.CONCEPTUAL,
                  prerequisites=[]),
        Objective("o3", "predict", "whether a transaction pair produces write skew "
                  "under Repeatable Read", Bloom.APPLY, KnowledgeType.PROCEDURAL,
                  condition="given two concurrent transactions",
                  criterion="correctly, with the invariant named",
                  prerequisites=["o2"]),
    ]


def test_clean_graph_passes_and_derives_order():
    r = validate(mvcc_graph())
    assert r.ok, r.render()
    assert r.teaching_order.index("o2") < r.teaching_order.index("o3")


def test_banned_verb_blocks_with_a_substitute():
    objs = mvcc_graph()
    objs[2] = Objective("o3", "understand", "write skew", Bloom.APPLY,
                        KnowledgeType.PROCEDURAL, prerequisites=["o2"])
    r = validate(objs)
    assert not r.ok
    f = next(f for f in r.findings if f.rule == "observable_verb")
    assert "cannot be observed" in f.message
    assert "predict" in (f.fix or "")


def test_verb_bloom_mismatch_blocks():
    """'list' is a remember-level verb; declaring it apply-level is the error
    that makes the whole alignment chain meaningless."""
    objs = [Objective("o1", "list", "isolation levels", Bloom.APPLY,
                      KnowledgeType.FACTUAL)]
    r = validate(objs)
    assert not r.ok
    assert any(f.rule == "verb_bloom_mismatch" for f in r.findings)


def test_unknown_verb_warns_but_does_not_block():
    objs = [Objective("o1", "grok", "snapshots", Bloom.UNDERSTAND,
                      KnowledgeType.CONCEPTUAL)]
    r = validate(objs)
    assert r.ok
    assert any(f.rule == "verb_whitelist" and not f.blocking for f in r.findings)


def test_cycle_is_a_hard_error():
    objs = [
        Objective("o1", "explain", "a", Bloom.UNDERSTAND, KnowledgeType.CONCEPTUAL,
                  prerequisites=["o2"]),
        Objective("o2", "explain", "b", Bloom.UNDERSTAND, KnowledgeType.CONCEPTUAL,
                  prerequisites=["o1"]),
    ]
    r = validate(objs)
    assert not r.ok
    assert any(f.rule == "prerequisite_cycle" for f in r.findings)


def test_unknown_prerequisite_blocks():
    objs = [Objective("o1", "predict", "write skew", Bloom.APPLY,
                      KnowledgeType.PROCEDURAL, prerequisites=["o99"])]
    r = validate(objs)
    assert not r.ok
    assert any(f.rule == "unknown_prerequisite" for f in r.findings)


def test_missing_assessment_blocks():
    r = validate(mvcc_graph(), items=[])
    assert not r.ok
    missing = {f.subject for f in r.findings if f.rule == "no_assessment"}
    assert missing == {"o2", "o3"}, "assumed o1 must be exempt"


def test_the_apply_assessed_as_remember_failure():
    """The specific failure §5.3 names: an Apply-level objective assessed by a
    Remember-level MCQ. This is the check that earns the linter its keep."""
    items = [
        AssessmentItem("a1", "o2", Bloom.UNDERSTAND, "mcq", "What does RR guarantee?"),
        AssessmentItem("a2", "o3", Bloom.REMEMBER, "mcq",
                       "Which isolation level is the strictest?"),
    ]
    r = validate(mvcc_graph(), items=items)
    assert not r.ok
    f = next(f for f in r.findings if f.rule == "bloom_misalignment")
    assert f.subject == "o3"
    assert "does not verify" in f.message


def test_aligned_assessment_passes():
    items = [
        AssessmentItem("a1", "o2", Bloom.UNDERSTAND, "mcq", "What does RR guarantee?"),
        AssessmentItem("a2", "o3", Bloom.APPLY, "predict",
                       "Two transactions each check the on-call count, then update. "
                       "Does the invariant hold under Repeatable Read?"),
    ]
    r = validate(mvcc_graph(), items=items)
    assert r.ok, r.render()


def test_report_renders_blocking_first():
    r = validate(mvcc_graph(), items=[])
    text = r.render()
    assert text.startswith("[BLOCK]")
    assert "fix:" in text

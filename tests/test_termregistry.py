"""The per-course term registry — ISSUE-7 and ISSUE-1, one piece of work.

Set membership, no thresholds, no model. The tests are about the boundary
conditions that make it either the course-memory primitive or a subtle lie:
video 1, ordering by teaching order rather than write order, and first-writer-
wins when two videos claim the same term.
"""
from __future__ import annotations

from explainer.termregistry import Registry, check_recall_slot

V1 = Registry(terms={"xmin": "v1", "snapshot": "v1", "repeatable read": "v1"},
              previous_video_objectives=("o4", "o5"),
              previous_video_ref="v1", up_to_ordinal=2)
FIRST = Registry(up_to_ordinal=1)


# ---------------------------------------------------------------- registry

def test_a_term_an_earlier_video_taught_is_known():
    assert V1.knows("snapshot")
    assert V1.taught_by("snapshot") == "v1"


def test_a_term_nobody_taught_is_not_known():
    assert not V1.knows("write skew")
    assert V1.taught_by("write skew") is None


def test_the_first_video_knows_nothing():
    assert FIRST.terms == {} and FIRST.previous_video_ref is None


def test_seen_is_a_copy_the_caller_may_mutate():
    """`first_use_only` mutates the set it is given; handing out the registry's
    own dict keys would corrupt the registry mid-video."""
    seen = V1.seen
    seen.add("write skew")
    assert "write skew" not in V1.terms


# ------------------------------------------------------------- the gate

def test_recall_naming_the_previous_video_s_objective_passes():
    assert not check_recall_slot("s03", "o4", ["snapshot"], V1)


def test_recall_naming_this_video_s_own_objective_fails():
    """The week-3 defect exactly: recalling what this video is about to teach."""
    problems = check_recall_slot("s03", "o6", [], V1)
    assert problems and "not taught by the previous video" in problems[0]
    assert "o4" in problems[0], "the error must name what IS available"


def test_recall_assuming_a_term_nobody_taught_fails():
    """The v2 s03 failure: 'non-repeatable read' and 'phantom' are v2's OWN
    new terms, presented as though the learner already had them."""
    problems = check_recall_slot("s03", "o4",
                                 ["non-repeatable read", "phantom"], V1)
    assert len(problems) == 2
    assert all("as already known" in p for p in problems)


def test_the_error_lists_what_is_known_so_a_repair_is_possible():
    problems = check_recall_slot("s03", "o4", ["phantom"], V1)
    assert "snapshot" in problems[0] and "xmin" in problems[0]


def test_the_first_video_may_not_assume_anything():
    problems = check_recall_slot("s03", "o1", ["snapshot"], FIRST)
    assert problems and "first video" in problems[0]


def test_the_first_video_with_an_empty_recall_passes():
    assert not check_recall_slot("s03", None, [], FIRST)


def test_a_partial_failure_reports_only_the_bad_terms():
    problems = check_recall_slot("s03", "o4", ["snapshot", "phantom"], V1)
    assert len(problems) == 1 and "phantom" in problems[0]

"""The Course Brief — §6 Stage 1.

Covers `factual_constraints`: statements the narration may not contradict,
supplied PER COURSE by the brief rather than hardcoded into a general prompt.
The structure is the point — see `test_constraints_live_on_the_brief_not_in_the_prompt`.
"""
from __future__ import annotations

from explainer.brief import Audience, CourseBrief


# ----------------------------------- factual constraints (per course, not prompt)

def test_factual_constraints_default_to_empty():
    b = CourseBrief(title="t", description="d", audience=Audience())
    assert b.factual_constraints == ()


def test_factual_constraints_survive_a_round_trip():
    b = CourseBrief(title="t", description="d", audience=Audience(),
                    factual_constraints=("a snapshot is taken at the first "
                                         "statement", "locks are not all equal"))
    back = CourseBrief.from_json(b.to_json())
    assert back.factual_constraints == b.factual_constraints


def test_factual_constraints_are_in_the_closure():
    """Changing what the narration may not contradict must invalidate the
    script, or a corrected constraint would serve the old wrong narration."""
    a = CourseBrief(title="t", description="d", audience=Audience())
    b = CourseBrief(title="t", description="d", audience=Audience(),
                    factual_constraints=("x",))
    assert a.to_closure() != b.to_closure()


def test_constraints_live_on_the_brief_not_in_the_prompt():
    """The structural point: they are topic-specific. A general prompt carrying
    one domain's semantics teaches every later course facts it does not need."""
    import pathlib
    prompt = (pathlib.Path(__file__).parents[1] / "prompts"
              / "script_writer.v4.md").read_text(encoding="utf-8")
    assert "factual_constraints" in prompt, "the prompt must reference the slot"
    for leaked in ("Repeatable Read", "PostgreSQL", "ACCESS EXCLUSIVE", "40001"):
        assert leaked not in prompt, (
            f"{leaked!r} is a topic fact and must come from the brief, not the "
            f"general prompt")

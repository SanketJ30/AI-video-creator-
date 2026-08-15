"""The Fact Challenger — §7.2, ISSUE-8.

No API calls: the parsing, thresholds and severity logic are what can be tested
deterministically. Whether the agent actually catches a false claim is not a
unit-test question — it is a POSITIVE CONTROL question, and the control lives in
`tests/gold/issue8_positive_control.json` with its result recorded in
`docs/week6-fact-challenger.md`.
"""
from __future__ import annotations

import json

import pytest

from explainer.agents import fact_challenger as fc
from explainer.agents.objective_extractor import SchemaError

SPANS = [{"id": "sp_aaaaaaaaaa", "text": "A writes A's row."},
         {"id": "sp_bbbbbbbbbb", "text": "Neither writes what the other reads."}]


def finding(**kw):
    base = {"span_id": "sp_bbbbbbbbbb", "claim": "c", "verdict": "refuted",
            "confidence": 0.9, "attack": "tried X, it broke",
            "correction": "should say Y", "contradicts": ""}
    base.update(kw)
    return base


def raw(*findings):
    return json.dumps({"findings": list(findings)})


# ------------------------------------------------------------------ parsing

def test_a_verdict_on_an_unknown_span_is_rejected():
    """R3 applied to findings: a verdict on a span that does not exist points a
    reviewer at nothing."""
    with pytest.raises(SchemaError) as e:
        fc.parse(raw(finding(span_id="sp_deadbeef00")), SPANS)
    assert "not in this scene" in str(e.value)


def test_every_verdict_needs_the_attack_that_produced_it():
    """A 'survives' with no attack described is not a result — it is the
    agreement this agent exists to avoid."""
    with pytest.raises(SchemaError) as e:
        fc.parse(raw(finding(verdict="survives", attack="", correction="")), SPANS)
    assert "attack" in str(e.value)


def test_a_refutation_must_say_what_a_correct_version_says():
    with pytest.raises(SchemaError) as e:
        fc.parse(raw(finding(correction="")), SPANS)
    assert "correct version" in str(e.value)


def test_a_survives_needs_no_correction():
    out = fc.parse(raw(finding(verdict="survives", correction="")), SPANS)
    assert out[0].verdict == "survives"


def test_an_unknown_verdict_is_rejected():
    with pytest.raises(SchemaError):
        fc.parse(raw(finding(verdict="probably_fine")), SPANS)


def test_confidence_must_be_a_number_in_range():
    for bad in (1.5, -0.1, "high", None):
        with pytest.raises(SchemaError):
            fc.parse(raw(finding(confidence=bad)), SPANS)


def test_an_empty_finding_list_is_valid():
    """A scene of questions and instructions carries no claims, and that is a
    normal result rather than a failure to try."""
    assert fc.parse(json.dumps({"findings": []}), SPANS) == []


def test_every_problem_is_reported_at_once():
    """A repair loop that fixes one error per round burns calls."""
    with pytest.raises(SchemaError) as e:
        fc.parse(raw(finding(span_id="sp_nope"), finding(verdict="wat")), SPANS)
    assert len(e.value.problems) == 2


# ---------------------------------------------------------------- severity

def test_a_confident_refutation_is_blocking():
    """§7.2: 'never silently kept'."""
    c = fc.parse(raw(finding(confidence=0.9)), SPANS)[0]
    assert c.blocking and c.severity == "blocking"


def test_a_low_confidence_refutation_is_demoted_not_discarded():
    """ISSUE-8's lesson: silence is the expensive failure. A refutation the
    agent is unsure of is still shown."""
    c = fc.parse(raw(finding(confidence=0.5)), SPANS)[0]
    assert not c.blocking
    assert c.severity == "warning", "must still reach the report"


def test_the_threshold_boundary_is_inclusive():
    at = fc.parse(raw(finding(confidence=fc.AUTHORED_MIN_CONFIDENCE)), SPANS)[0]
    assert at.blocking


def test_unsupported_is_a_warning_and_survives_is_info():
    u = fc.parse(raw(finding(verdict="unsupported", correction="")), SPANS)[0]
    s = fc.parse(raw(finding(verdict="survives", correction="")), SPANS)[0]
    assert u.severity == "warning" and s.severity == "info"


def test_the_threshold_is_marked_authored():
    import inspect
    src = inspect.getsource(fc)
    assert "AUTHORED AND UNREVIEWED" in src
    assert fc.AUTHORED_MIN_CONFIDENCE == 0.70


def test_the_threshold_gates_the_agents_confidence_not_the_claim():
    """Worth pinning because the two are easy to conflate: this number is the
    agent's confidence in its OWN verdict, not a probability the claim is
    false."""
    import inspect
    doc = inspect.getdoc(fc) or ""
    assert "not the truth of" in doc or "does NOT decide whether a claim is false" in doc


# ------------------------------------------------------------------ report

def test_a_report_with_a_blocking_finding_is_not_ok():
    r = fc.ChallengeReport(scenes={"s04": fc.parse(raw(finding()), SPANS)})
    assert not r.ok and len(r.blocking) == 1


def test_a_report_of_survivals_is_ok():
    r = fc.ChallengeReport(scenes={"s04": fc.parse(
        raw(finding(verdict="survives", correction="")), SPANS)})
    assert r.ok


def test_the_render_names_the_span_not_the_scene():
    """A verdict on a scene tells a reviewer to re-read ninety seconds."""
    r = fc.ChallengeReport(scenes={"s04": fc.parse(raw(finding()), SPANS)})
    for c in r.all:
        c.scene_ref = "s04"
    assert "sp_bbbbbbbbbb" in r.render()


def test_a_contradiction_names_the_other_span():
    c = fc.parse(raw(finding(contradicts="sp_aaaaaaaaaa")), SPANS)[0]
    assert c.contradicts == "sp_aaaaaaaaaa"
    assert "sp_aaaaaaaaaa" in c.to_json()["contradicts"]


# --------------------------------------------------- the positive control

def test_the_positive_control_fixture_still_contains_the_known_false_claim():
    """The control is only a control while it holds the specimen. If someone
    'tidies' this fixture, the checker silently stops being tested."""
    import pathlib
    doc = json.loads((pathlib.Path(__file__).parent / "gold"
                      / "issue8_positive_control.json").read_text(encoding="utf-8"))
    spans = {s["id"]: s["text"] for s in doc[0]["spans"]}
    assert spans["sp_b735cd9656"] == (
        "Neither transaction writes the row the other one reads.")

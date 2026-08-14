"""The §14.4 regression harness.

The checks and the k-of-n arithmetic are deterministic, so all of this runs
offline. The point of the module is that a finding survives repetition, so the
tests are mostly about the harness reporting a spread honestly rather than
collapsing it to a single verdict.
"""
from __future__ import annotations

import json

import pytest

from explainer import harness
from explainer.brief import CourseBrief
from explainer.harness import CheckSpec
from explainer.objectives import Bloom, KnowledgeType, Objective
from tests.test_objective_extraction import FakeClient


def obj(ref, bloom=Bloom.APPLY, ktype="conceptual", assumed=False,
        criterion=None, object_="write skew under Repeatable Read"):
    return Objective(ref=ref, verb="predict", object=object_, bloom_level=bloom,
                     knowledge_type=KnowledgeType(ktype), criterion=criterion,
                     assumed=assumed)


# ------------------------------------------------------------- the checks

def test_mentions_all_uses_word_boundaries():
    """A bare substring test reported 'ssi' present because 'sessions' contains
    it. That false positive is the reason this check exists as code."""
    objs = [obj("o1", criterion="two sessions PostgreSQL assigns ids")]
    ok, detail = harness.check_mentions_all(objs, ["ssi"])
    assert not ok and "ssi" in detail


def test_mentions_all_finds_terms_in_the_criterion():
    objs = [obj("o1", criterion="naming dirty read, non-repeatable read and "
                                "phantom read")]
    ok, _ = harness.check_mentions_all(
        objs, ["dirty read", "non-repeatable read", "phantom read"])
    assert ok


def test_mentions_all_reports_which_term_is_missing():
    objs = [obj("o1", criterion="naming dirty read and non-repeatable read")]
    ok, detail = harness.check_mentions_all(
        objs, ["dirty read", "non-repeatable read", "phantom read"])
    assert not ok and "phantom read" in detail


def test_mentions_none_is_the_inverse():
    objs = [obj("o1", criterion="SERIALIZABLE aborts one transaction")]
    assert not harness.check_mentions_none(objs, ["serializable"])[0]
    assert harness.check_mentions_none(objs, ["phantom read"])[0]


def test_taught_count_ignores_assumed_objectives():
    objs = [obj("o1"), obj("o2"), obj("a1", assumed=True), obj("a2", assumed=True)]
    ok, detail = harness.check_taught_count(objs, min=1, max=2)
    assert ok and "2 taught" in detail


def test_taught_count_fails_the_v1_granularity_shape():
    objs = [obj(f"o{i}") for i in range(1, 11)]
    ok, detail = harness.check_taught_count(objs, min=1, max=2)
    assert not ok and "10 taught" in detail


def test_max_taught_bloom_looks_at_the_highest_not_the_first():
    objs = [obj("o1", Bloom.REMEMBER), obj("o2", Bloom.ANALYZE)]
    assert harness.check_max_taught_bloom(objs, level="analyze")[0]
    assert not harness.check_max_taught_bloom(objs, level="remember")[0]


def test_an_unknown_check_names_the_rule_it_would_break():
    with pytest.raises(harness.UnknownCheck) as e:
        harness.run_check("vibes", [obj("o1")], {})
    assert "deterministic function" in str(e.value)


# --------------------------------------------------------- k-of-n verdicts

def _graph_json(criterion: str, count: int = 2) -> str:
    objs = []
    for i in range(1, count + 1):
        objs.append({
            "ref": f"o{i}", "verb": "predict",
            "object": "whether write skew occurs", "condition": "",
            "criterion": criterion if i == count else "",
            "bloom_level": "apply", "knowledge_type": "conceptual",
            "assumed": False, "prerequisites": [],
            "rationale": "r",
            "learner_facing_statement": "You'll spot the case that breaks the rule."})
    return json.dumps({"objectives": objs, "assessment_items": [], "out_of_scope": ""})


ALL_THREE = "naming dirty read, non-repeatable read and phantom read"
SPEC = [CheckSpec(name="mentions_all",
                  params={"terms": ["dirty read", "non-repeatable read",
                                    "phantom read"]},
                  label="names all three anomalies")]


def _run(criteria: list[str], pass_k=2):
    client = FakeClient([_graph_json(c) for c in criteria])
    return harness.run(None, None, CourseBrief(title="t"), SPEC,
                       config="test", samples=len(criteria), pass_k=pass_k,
                       client=client)


def test_three_of_three_passes():
    r = _run([ALL_THREE] * 3)
    assert r.hits("names all three anomalies") == 3
    assert r.passed("names all three anomalies")
    assert "met in 3 of 3 — PASSES" in r.verdict("names all three anomalies")


def test_two_of_three_passes_at_the_stated_threshold():
    """Sanket's criterion: met in at least 2 of 3."""
    r = _run([ALL_THREE, ALL_THREE, "naming nothing in particular"])
    assert r.verdict("names all three anomalies") == "met in 2 of 3 — PASSES"


def test_one_of_three_fails():
    """The real v3-run4 shape: one sample met it, two did not."""
    r = _run([ALL_THREE, "naming nothing", "naming nothing"])
    assert r.verdict("names all three anomalies") == "met in 1 of 3 — FAILS"


def test_the_spread_is_preserved_not_collapsed():
    """A harness that reported only the verdict would hide the thing that made
    it necessary."""
    r = _run([ALL_THREE, "naming nothing", ALL_THREE])
    per_sample = [s.checks["names all three anomalies"][0] for s in r.samples]
    assert per_sample == [True, False, True]
    assert "sample 2: fail" in r.render()


def test_every_sample_is_an_independent_call():
    client = FakeClient([_graph_json(ALL_THREE) for _ in range(3)])
    harness.run(None, None, CourseBrief(title="t"), SPEC, config="t",
                samples=3, client=client)
    assert len(client.messages.calls) == 3, "a cached sample measures no spread"


def test_cost_is_summed_across_samples():
    r = _run([ALL_THREE] * 3)
    assert r.cost_usd == round(sum(s.cost_usd for s in r.samples), 6)


def test_the_yaml_fragment_records_per_sample_results():
    r = _run([ALL_THREE, "nothing", "nothing"])
    frag = r.to_yaml_fragment()
    assert "samples: 3" in frag
    assert "pass_criterion: met in at least 2 of 3" in frag
    assert "results: [true, false, false]" in frag
    assert "verdict: met in 1 of 3 — FAILS" in frag
    assert "harness_cost_usd:" in frag


def test_defaults_match_the_stated_threshold():
    assert harness.DEFAULT_SAMPLES == 3
    assert harness.DEFAULT_PASS_K == 2

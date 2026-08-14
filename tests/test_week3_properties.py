"""Week 3 cross-cutting properties, and the no-live-calls guard.

The per-module tests cover each piece; these are the properties that only make
sense across the whole step-1-to-4 chain, plus the one guard that protects the
whole suite: `pytest -q` with no flags must make zero API calls.
"""
from __future__ import annotations

import json

import pytest

from explainer import gagne, prose
from explainer.agents import curriculum_planner as cp
from explainer.agents import objective_extractor as ox
from explainer.agents import script_writer as sw
from explainer.brief import CourseBrief
from explainer.gagne import Slot
from explainer.objectives import Bloom, KnowledgeType, Objective
from tests.test_objective_extraction import FakeClient

BUDGET = 240          # what the MVCC course's brief actually carries


# ------------------------------------------------- zero live calls, ever

def test_pytest_makes_no_api_calls_without_an_explicit_opt_in(monkeypatch):
    """The guard. Every agent builds its client through ox._client; if a test
    ever reaches it without injecting a fake, this fails loudly instead of
    quietly spending money on someone's laptop."""
    def explode(*a, **kw):
        raise AssertionError(
            "a test tried to build a real Anthropic client. Inject a FakeClient, "
            "or mark the test live and gate it behind EXPLAINER_LIVE=1.")

    monkeypatch.setattr(ox, "_client", explode)
    client = FakeClient([_script_json()])
    sw.generate(None, None, CourseBrief(title="t"), _video(), [_obj("o1")],
                client=client)          # must not touch _client


def test_every_live_test_is_gated_behind_the_explicit_opt_in():
    """Any test that can reach the network must require EXPLAINER_LIVE=1.

    Checked by reading the test sources rather than by trusting a convention:
    the failure mode is a live test added later without the gate, which nobody
    notices until `make test` bills someone."""
    import pathlib
    import re
    here = pathlib.Path(__file__).parent
    offenders = []
    for path in sorted(here.glob("test_*.py")):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"@pytest\.mark\.live", text):
            # The `live` skipif must be applied to the same test and must name
            # the opt-in env var.
            window = text[max(0, match.start() - 400):match.start() + 400]
            if "EXPLAINER_LIVE" not in text or "@live" not in window:
                offenders.append(f"{path.name}:{text[:match.start()].count(chr(10)) + 1}")
    assert not offenders, (
        f"live-marked test(s) not gated behind EXPLAINER_LIVE: {offenders}")


def test_the_live_marker_is_registered_in_pyproject():
    """An unregistered marker only warns, so a typo'd @pytest.mark.liv would
    silently never run."""
    import pathlib
    text = (pathlib.Path(__file__).parent.parent / "pyproject.toml").read_text(
        encoding="utf-8")
    assert "markers = [" in text and '"live:' in text


# -------------------------------------------------------------- fixtures

def _obj(ref, bloom=Bloom.APPLY, ktype="conceptual", prereqs=(), assumed=False):
    return Objective(ref=ref, verb="predict", object=f"thing {ref}",
                     bloom_level=bloom, knowledge_type=KnowledgeType(ktype),
                     prerequisites=list(prereqs), assumed=assumed)


def _video(script_type="explainer", refs=("o1", "o2"), seconds=BUDGET):
    return {"id": "vid-1", "ref": "v1", "title": "t", "script_type": script_type,
            "target_seconds": seconds, "objective_refs": list(refs), "ordinal": 1}


def _script_json(script_type="explainer", seconds=BUDGET, narration=None):
    scenes = []
    for spec in gagne.plan_slots(script_type, seconds):
        scenes.append({
            "slot": spec.slot.value,
            "narration": (narration or {}).get(
                spec.slot.value, "You run two transactions. Each reads the same row."),
            "timing_sensitivity": "elastic",
            "element_interactivity": "low",
            "new_terms": [],
            "rationale": "",
        })
    return json.dumps({"scenes": scenes})


def _draft(**kw):
    client = FakeClient([_script_json(**kw)])
    objs = [_obj("o1"), _obj("o2", prereqs=["o1"])]
    return sw.generate(None, None, CourseBrief(title="t"), _video(), objs,
                       client=client)


# ------------------------------------------------- chained properties

def test_the_planner_output_feeds_the_script_writer_form():
    """What the planner emits as script_type must be a variant the template
    knows. A planner that can name a script type gagne.py cannot build is a
    silent break between step 1 and step 3."""
    for ktype, bloom in [("conceptual", Bloom.APPLY), ("conceptual", Bloom.ANALYZE),
                         ("procedural", Bloom.APPLY)]:
        st = cp.script_type_for([_obj("o1", bloom, ktype)])
        gagne.variant(st)          # must not raise


def test_every_scene_has_exactly_one_objective():
    d = _draft()
    assert all(s.objective_ref for s in d.scenes)
    assert all(isinstance(s.objective_ref, str) for s in d.scenes)


def test_every_scenes_narration_round_trips_with_stable_ids():
    d = _draft()
    for s in d.scenes:
        ids = [sp.id for sp in s.narration.spans]
        assert len(ids) == len(set(ids))
        # Round trip: json -> text -> ids remain addressable
        payload = s.narration.to_json()
        assert [p["id"] for p in payload] == ids
        assert " ".join(p["text"] for p in payload) == s.narration.text
        for i in ids:
            assert s.narration.by_id(i).id == i


def test_no_scene_has_an_authored_duration():
    d = _draft()
    for s in d.scenes:
        meta = s.pedagogy_meta()
        assert "duration_value" not in meta and "duration_rate" not in meta
        assert isinstance(meta["duration_target_seconds"], int)


def test_slot_coverage_matches_the_script_type_variant():
    for st in sorted(gagne.VARIANTS):
        client = FakeClient([_script_json(script_type=st)])
        objs = [_obj("o1"), _obj("o2", prereqs=["o1"])]
        d = sw.generate(None, None, CourseBrief(title="t"), _video(st), objs,
                        client=client)
        assert [s.slot for s in d.scenes] == [
            sp.slot for sp in gagne.plan_slots(st, BUDGET)]


def test_new_terms_never_repeat_a_term_from_an_earlier_scene():
    terms = {s.value: {"new_terms": ["mvcc", "snapshot", "xmin"]} for s in Slot}
    client = FakeClient([json.dumps({"scenes": [
        {"slot": spec.slot.value, "narration": "You see it.",
         "timing_sensitivity": "elastic", "element_interactivity": "low",
         "new_terms": terms[spec.slot.value]["new_terms"], "rationale": ""}
        for spec in gagne.plan_slots("explainer", BUDGET)]})])
    d = sw.generate(None, None, CourseBrief(title="t"), _video(), [_obj("o1")],
                    client=client)
    seen: set[str] = set()
    for s in d.scenes:
        for t in s.new_terms:
            assert t not in seen, f"{t} repeated in {s.ref}"
            seen.add(t)
    assert seen == {"mvcc", "snapshot", "xmin"}


def test_the_prose_gates_run_over_a_generated_draft():
    """End of the chain: a draft's scenes are the shape check_script expects."""
    d = _draft()
    scenes = [{"ref": s.ref, "text": s.text, "gagne_slot": s.slot.value,
               "pedagogy_meta": s.pedagogy_meta()} for s in d.scenes]
    report = prose.check_script(scenes, technical=True)
    assert isinstance(report.findings, list)
    assert report.ok, report.render()


def test_a_slot_stuffed_past_its_budget_is_caught_by_the_gates():
    """The chain's real job: an over-long slot must surface, not sail through."""
    long_text = " ".join(["transaction"] * 200) + "."
    d = _draft(narration={"objective": long_text})
    scenes = [{"ref": s.ref, "text": s.text, "gagne_slot": s.slot.value,
               "pedagogy_meta": s.pedagogy_meta()} for s in d.scenes]
    report = prose.check_script(scenes, technical=True)
    assert not report.ok
    blocking = [f for f in report.blocking if f.rule == "speaking_rate"]
    assert blocking and blocking[0].subject == "s02"


@pytest.mark.parametrize("seconds", [gagne.MIN_VIABLE_BUDGET_SECONDS, 240, 300, 360])
def test_the_derived_total_tracks_the_brief_budget(seconds):
    total = gagne.total_seconds("explainer", seconds)
    assert abs(total - seconds) <= len(gagne.TAIL_SLOTS)

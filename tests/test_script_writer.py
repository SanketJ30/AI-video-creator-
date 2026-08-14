"""Script writer — §6 Stage 2c, §5.3, CHALLENGES R4/R5/R6.

Structural properties only. Nothing here asserts the narration is any good —
that is what the prose gates and a human at Gate A are for.
"""
from __future__ import annotations

import json

import pytest

from explainer import gagne
from explainer.agents import script_writer as sw
from explainer.brief import CourseBrief
from explainer.gagne import Slot
from explainer.objectives import Bloom, KnowledgeType, Objective
from tests.test_objective_extraction import FakeClient

BUDGET = 300


def obj(ref, bloom=Bloom.APPLY, ktype="conceptual", prereqs=(), assumed=False):
    return Objective(ref=ref, verb="predict", object=f"thing {ref}",
                     bloom_level=bloom, knowledge_type=KnowledgeType(ktype),
                     prerequisites=list(prereqs), assumed=assumed)


def video(script_type="explainer", refs=("o1",), seconds=BUDGET):
    return {"id": "vid-1", "ref": "v1", "title": "When Repeatable Read isn't enough",
            "script_type": script_type, "target_seconds": seconds,
            "objective_refs": list(refs), "ordinal": 1}


def script_json(overrides: dict | None = None, script_type="explainer"):
    """A well-formed response filling every slot in the form."""
    overrides = overrides or {}
    scenes = []
    for spec in gagne.plan_slots(script_type, BUDGET):
        name = spec.slot.value
        base = {
            "slot": name,
            "narration": f"You'll see how {name} works. It's short and clear.",
            "timing_sensitivity": "elastic",
            "element_interactivity": "low",
            "new_terms": [],
            "rationale": f"the {name} slot's job",
        }
        base.update(overrides.get(name, {}))
        scenes.append(base)
    return json.dumps({"scenes": scenes})


def draft(overrides=None, objectives=None, script_type="explainer", refs=("o1",)):
    objectives = objectives or [obj("o1")]
    client = FakeClient([script_json(overrides, script_type)])
    return sw.generate(None, None, CourseBrief(title="t"),
                       video(script_type, refs), objectives, client=client)


# ------------------------------------------------------------- new terms

def test_new_terms_are_computed_in_code_not_taken_from_the_model():
    """A term claimed twice is new once. The model is asked, but the set wins."""
    d = draft({
        "hook": {"new_terms": ["Write Skew", "snapshot"]},
        "present": {"new_terms": ["write skew", "xmin"]},
        "guide": {"new_terms": ["write skew."]},
    })
    by_slot = {s.slot.value: s for s in d.scenes}
    assert by_slot["hook"].new_terms == ["write skew", "snapshot"]
    assert by_slot["present"].new_terms == ["xmin"], "write skew was already used"
    assert by_slot["guide"].new_terms == []


def test_a_term_never_repeats_across_scenes():
    d = draft({s.value: {"new_terms": ["mvcc", "snapshot"]} for s in Slot})
    seen = [t for s in d.scenes for t in s.new_terms]
    assert len(seen) == len(set(seen)), f"repeated terms: {seen}"
    assert seen == ["mvcc", "snapshot"]


def test_the_models_own_claim_is_kept_for_review():
    d = draft({"present": {"new_terms": ["MVCC"]}, "guide": {"new_terms": ["MVCC"]}})
    guide = next(s for s in d.scenes if s.slot is Slot.GUIDE)
    assert guide.new_terms == []
    assert guide.pedagogy_meta()["model_claimed_new_terms"] == ["mvcc"]


def test_normalise_term_folds_case_and_punctuation():
    assert sw.normalise_term("Repeatable Read.") == "repeatable read"
    assert sw.normalise_term("  XMIN  ") == "xmin"


# ----------------------------------------------------------------- spans

def test_narration_is_segmented_into_spans_at_authoring_time():
    """R4: spans are the join key; they exist before anything downstream runs."""
    d = draft({"hook": {"narration": "Two transactions read the same rows. "
                                     "Neither sees the other's write."}})
    hook = next(s for s in d.scenes if s.slot is Slot.HOOK)
    assert len(hook.narration.spans) == 2
    assert all(sp.id.startswith("sp_") for sp in hook.narration.spans)


def test_span_ids_are_unique_within_a_scene_and_round_trip():
    d = draft()
    for s in d.scenes:
        ids = [sp.id for sp in s.narration.spans]
        assert len(ids) == len(set(ids))
        for sp in s.narration.spans:
            assert s.narration.by_id(sp.id) is sp


def test_narration_json_is_span_objects_not_flat_prose():
    d = draft()
    payload = d.scenes[0].narration.to_json()
    assert isinstance(payload, list)
    assert {"id", "text"} <= set(payload[0])


# ------------------------------------------------------------- durations

def test_no_scene_carries_an_authored_duration():
    """R5: duration is derived from TTS. Nothing here may author one."""
    d = draft()
    for s in d.scenes:
        assert not hasattr(s, "duration_value")
        assert "duration_value" not in s.pedagogy_meta()
        assert "duration_rate" not in s.pedagogy_meta()


def test_the_slot_budget_is_recorded_as_a_target_not_a_duration():
    d = draft()
    by_slot = {s.slot: s for s in d.scenes}
    form = {sp.slot: sp.seconds for sp in gagne.plan_slots("explainer", BUDGET)}
    for slot, scene in by_slot.items():
        assert scene.pedagogy_meta()["duration_target_seconds"] == form[slot]


# ---------------------------------------------------------- one objective

def test_every_scene_has_exactly_one_objective():
    d = draft(objectives=[obj("o1")])
    assert all(isinstance(s.objective_ref, str) and s.objective_ref for s in d.scenes)
    assert {s.objective_ref for s in d.scenes} == {"o1"}


def test_two_objectives_split_structurally_across_the_slots():
    """§5.3 allows two objectives on a video but exactly one per scene."""
    objs = [obj("o1"), obj("o2", prereqs=["o1"])]
    d = draft(objectives=objs, refs=("o1", "o2"))
    by_slot = {s.slot: s.objective_ref for s in d.scenes}
    assert by_slot[Slot.HOOK] == "o1"
    assert by_slot[Slot.PRESENT] == "o1"
    assert by_slot[Slot.GUIDE] == "o2"
    assert by_slot[Slot.RETAIN] == "o2"
    assert len({s.objective_ref for s in d.scenes}) == 2


# ------------------------------------------------------------ slot form

def test_slot_coverage_matches_the_variant_form():
    for script_type in ("explainer", "procedure_demo", "myth_busting"):
        d = draft(script_type=script_type)
        expected = [sp.slot for sp in gagne.plan_slots(script_type, BUDGET)]
        assert [s.slot for s in d.scenes] == expected


def test_scenes_come_back_in_form_order_not_response_order():
    """The model may emit slots in any order; the form decides."""
    form = gagne.plan_slots("explainer", BUDGET)
    scenes = [{"slot": sp.slot.value, "narration": "You'll see it.",
               "timing_sensitivity": "elastic", "element_interactivity": "low",
               "new_terms": [], "rationale": ""} for sp in reversed(form)]
    client = FakeClient([json.dumps({"scenes": scenes})])
    d = sw.generate(None, None, CourseBrief(title="t"), video(), [obj("o1")],
                    client=client)
    assert [s.slot for s in d.scenes] == [sp.slot for sp in form]
    assert [s.ordinal for s in d.scenes] == list(range(1, len(form) + 1))


def test_a_missing_slot_is_a_schema_error():
    form = gagne.plan_slots("explainer", BUDGET)
    scenes = [{"slot": sp.slot.value, "narration": "x",
               "timing_sensitivity": "elastic", "element_interactivity": "low",
               "new_terms": [], "rationale": ""} for sp in form[:-1]]
    with pytest.raises(sw.ox.SchemaError) as e:
        sw.parse(json.dumps({"scenes": scenes}), form)
    assert "not filled" in str(e.value)


def test_a_duplicated_slot_is_a_schema_error():
    form = gagne.plan_slots("explainer", BUDGET)
    scenes = [{"slot": "hook", "narration": "x", "timing_sensitivity": "elastic",
               "element_interactivity": "low", "new_terms": [], "rationale": ""}] * 2
    with pytest.raises(sw.ox.SchemaError) as e:
        sw.parse(json.dumps({"scenes": scenes}), form)
    assert "more than once" in str(e.value)


def test_an_invented_slot_is_a_schema_error():
    form = gagne.plan_slots("explainer", BUDGET)
    scenes = [{"slot": "outro", "narration": "x", "timing_sensitivity": "elastic",
               "element_interactivity": "low", "new_terms": [], "rationale": ""}]
    with pytest.raises(sw.ox.SchemaError) as e:
        sw.parse(json.dumps({"scenes": scenes}), form)
    assert "not in this video's form" in str(e.value)


# --------------------------------------------------------------- fields

def test_timing_sensitivity_defaults_to_elastic_and_rigid_is_carried():
    d = draft({"guide": {"timing_sensitivity": "rigid"}})
    by_slot = {s.slot: s for s in d.scenes}
    assert by_slot[Slot.GUIDE].timing_sensitivity == "rigid"
    assert by_slot[Slot.HOOK].timing_sensitivity == "elastic"


def test_pedagogy_meta_carries_bloom_and_interactivity():
    d = draft({"present": {"element_interactivity": "high"}},
              objectives=[obj("o1", Bloom.APPLY)])
    present = next(s for s in d.scenes if s.slot is Slot.PRESENT)
    meta = present.pedagogy_meta()
    assert meta["bloom_level"] == "apply"
    assert meta["element_interactivity"] == "high"


def test_provenance_is_recorded(monkeypatch):
    d = draft()
    p = d.provenance
    assert p["agent"] == "script_writer"
    assert p["prompt_version"].startswith("script_writer@v")
    assert "written_at" in p and p["model_version"]


def test_the_pinned_mid_tier_model_is_used():
    from explainer.config import settings
    client = FakeClient([script_json()])
    sw.generate(None, None, CourseBrief(title="t"), video(), [obj("o1")],
                client=client)
    assert client.messages.calls[0]["model"] == settings().models.mid


def test_a_schema_failure_gets_a_repair_round_trip():
    client = FakeClient(["not json", script_json()])
    d = sw.generate(None, None, CourseBrief(title="t"), video(), [obj("o1")],
                    client=client)
    assert len(d.attempts) == 2


def test_an_unusable_budget_raises_before_any_model_call():
    client = FakeClient([])          # any call would blow up
    with pytest.raises(gagne.BudgetError):
        sw.generate(None, None, CourseBrief(title="t"),
                    video(seconds=140), [obj("o1")], client=client)
    assert not client.messages.calls

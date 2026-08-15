"""Visual planner — §6 Stage 3, §8's animate-vs-static rule, §9.1, §10.

The gate under test is §8's. Code cannot decide whether a referent genuinely
changes over time, so what is tested is that the claim must be explicit and
internally consistent — and that an inconsistent claim is rejected rather than
softened into a warning.
"""
from __future__ import annotations

import json

import pytest

from explainer import templates
from explainer.agents import visual_planner as vp
from explainer.brief import CourseBrief
from explainer.objectives import Bloom, KnowledgeType, Objective
from tests.test_objective_extraction import FakeClient


def obj(ref="o1", bloom=Bloom.APPLY):
    return Objective(ref=ref, verb="predict", object="what each statement reads",
                     bloom_level=bloom, knowledge_type=KnowledgeType.CONCEPTUAL)


def scene(ref="s01", slot="present", seconds=90, text="You see two transactions."):
    return {"ref": ref, "gagne_slot": slot, "text": text, "objective_ref": "o1",
            "pedagogy_meta": {"duration_target_seconds": seconds,
                              "bloom_level": "apply", "element_interactivity": "high",
                              "new_terms": []}}


def video():
    return {"id": "vid-1", "ref": "v2", "title": "t", "script_type": "explainer",
            "target_seconds": 240}


def plan_json(entries):
    return json.dumps({"scenes": entries})


def entry(ref="s01", template="table_build", slots=None, motion="static_reveal",
          changes=False, what_changes="", rationale="r", state="neutral"):
    # A DESIGNED template (ISSUE-20): the planner is only offered templates
    # with a §9 layout, so a fixture using an undesigned one is now rejected.
    import json as _j
    return {"scene_ref": ref, "template": template,
            "slots_json": _j.dumps(slots if slots is not None
                                   else {"columns": ["Option", "Cost"],
                                         "rows": [{"cells": ["SERIALIZABLE",
                                                             "retry"]}]}),
            "motion": motion, "resolution_state": state,
            "referent_changes_over_time": changes,
            "what_changes": what_changes, "rationale": rationale}


def run(entries, scenes=None):
    scenes = scenes or [scene()]
    client = FakeClient([plan_json(entries)])
    return vp.plan(None, None, CourseBrief(title="t"), video(), scenes, [obj()],
                   client=client)


# ------------------------------------------------ the animate/static gate

def test_static_reveal_is_the_default_and_passes():
    p = run([entry()])
    assert p.scenes[0].motion == "static_reveal"


def test_animate_without_a_changing_referent_is_rejected():
    """§8: animate only if the referent genuinely changes over time."""
    problems = vp.check_motion("s01", "animate", False, "the diagram appears")
    assert any("referent_changes_over_time is false" in p for p in problems)


def test_animate_without_naming_what_changes_is_rejected():
    """A scene claiming motion must name the thing that moves — otherwise the
    claim is unfalsifiable and the gate does nothing."""
    problems = vp.check_motion("s01", "animate", True, "   ")
    assert any("what_changes is empty" in p for p in problems)


def test_animate_with_a_named_change_passes():
    assert not vp.check_motion(
        "s01", "animate", True,
        "the visible row version changes from xmin 100 to xmin 105 as T2 commits")


def test_claiming_change_without_naming_it_is_rejected_even_when_static():
    problems = vp.check_motion("s01", "static_reveal", True, "")
    assert any("say what changes" in p for p in problems)


def test_the_gate_rejects_through_the_repair_loop_not_as_a_finding():
    """A bad motion claim is structural: it goes back to the model rather than
    reaching a human as something to chase."""
    bad = entry(motion="animate", changes=False)
    good = entry()
    client = FakeClient([plan_json([bad]), plan_json([good])])
    p = vp.plan(None, None, CourseBrief(title="t"), video(), [scene()], [obj()],
                client=client)
    assert len(p.attempts) == 2
    assert "referent_changes_over_time is false" in p.attempts[0].error


def test_an_unknown_motion_value_is_rejected():
    assert vp.check_motion("s01", "shimmer", True, "x")


# ------------------------------------------------------- template choice

def test_an_unknown_template_is_rejected():
    with pytest.raises(vp.ox.SchemaError) as e:
        vp.parse(plan_json([entry(template="RemotionDiagram")]), [scene()])
    assert "no template" in str(e.value)


def test_slots_are_validated_against_the_chosen_template():
    with pytest.raises(vp.ox.SchemaError) as e:
        vp.parse(plan_json([entry(template="key_phrase", slots={})]), [scene()])
    assert "'phrase' is required" in str(e.value)


def test_malformed_slots_json_is_reported():
    """The API cannot validate a per-template parameter set, so this check is
    the only thing standing between a typo and a broken visual_spec."""
    bad = entry()
    bad["slots_json"] = "{not json"
    with pytest.raises(vp.ox.SchemaError) as e:
        vp.parse(plan_json([bad]), [scene()])
    assert "not valid JSON" in str(e.value)


def test_slots_json_decoding_to_a_non_object_is_reported():
    bad = entry()
    bad["slots_json"] = '["nodes"]'
    with pytest.raises(vp.ox.SchemaError) as e:
        vp.parse(plan_json([bad]), [scene()])
    assert "not an object" in str(e.value)


def test_a_template_outside_its_duration_band_is_rejected():
    """key_phrase holds 3-20s; a 90s present slot is not it."""
    with pytest.raises(vp.ox.SchemaError) as e:
        vp.parse(plan_json([entry(template="key_phrase",
                                  slots={"phrase": "snapshot, frozen"})]),
                 [scene(seconds=90)])
    assert "holds 3-20s" in str(e.value)


def test_a_template_inside_its_band_is_accepted():
    plans = vp.parse(plan_json([entry(template="key_phrase",
                                      slots={"phrase": "snapshot, frozen"})]),
                     [scene(seconds=10)])
    assert plans[0].template.name == "key_phrase"


def test_slot_item_limits_from_section_9_3_are_enforced():
    """§9.3 caps what a layout holds legibly. table_build allows 8 rows."""
    with pytest.raises(vp.ox.SchemaError) as e:
        vp.parse(plan_json([entry(slots={
            "columns": ["Option", "Cost"],
            "rows": [{"cells": [f"opt{i}", "x"]} for i in range(9)]})]),
            [scene()])
    assert "more than the 8" in str(e.value)


# --------------------------------------------------------- completeness

def test_every_scene_must_be_planned():
    """§9.2's multimedia rule: no narration over a static title for >8s."""
    with pytest.raises(vp.ox.SchemaError) as e:
        vp.parse(plan_json([entry("s01")]), [scene("s01"), scene("s02")])
    assert "not planned" in str(e.value) and "s02" in str(e.value)


def test_a_scene_planned_twice_is_rejected():
    with pytest.raises(vp.ox.SchemaError) as e:
        vp.parse(plan_json([entry("s01"), entry("s01")]), [scene("s01")])
    assert "more than once" in str(e.value)


def test_a_scene_ref_that_is_not_in_this_video_is_rejected():
    with pytest.raises(vp.ox.SchemaError) as e:
        vp.parse(plan_json([entry("s99")]), [scene("s01")])
    assert "not one of this video's scenes" in str(e.value)


def test_plans_come_back_in_scene_order():
    scenes = [scene("s01"), scene("s02"), scene("s03")]
    plans = vp.parse(plan_json([entry("s03"), entry("s01"), entry("s02")]), scenes)
    assert [p.scene_ref for p in plans] == ["s01", "s02", "s03"]


# ------------------------------------------------------------ visualSpec

def test_visual_spec_matches_the_section_5_1_shape():
    p = run([entry()])
    spec = p.scenes[0].visual_spec(p.provenance)
    assert {"template", "slots", "cues", "captionSafeArea"} <= set(spec)


def test_cues_is_present_and_empty_for_the_signal_designer():
    """A key that appears only later is a key downstream code cannot rely on."""
    p = run([entry()])
    assert p.scenes[0].visual_spec(p.provenance)["cues"] == []


def test_the_caption_safe_area_comes_from_the_template_not_the_model():
    """§16.2 + CHALLENGES: it is a property, and the model has no say."""
    p = run([entry()])
    spec = p.scenes[0].visual_spec(p.provenance)
    assert spec["captionSafeArea"] == templates.get(
        "table_build").safe_area.to_json()
    assert spec["captionSafeArea"]["bottom"] == templates.CAPTION_SAFE_BOTTOM


def test_every_decision_is_named_and_carries_its_rule():
    """§10: every AI decision is a named, addressable, overridable object."""
    p = run([entry()])
    decisions = p.scenes[0].visual_spec(p.provenance)["decisions"]
    assert {"template", "motion", "caption_safe_area"} <= set(decisions)
    for name, d in decisions.items():
        assert d["rule"], f"decision '{name}' does not say which rule produced it"


def test_provenance_is_recorded():
    p = run([entry()])
    assert p.provenance["agent"] == "visual_planner"
    assert p.provenance["prompt_version"].startswith("visual_planner@v")
    assert "planned_at" in p.provenance


def test_the_pinned_mid_tier_model_is_used():
    from explainer.config import settings
    client = FakeClient([plan_json([entry()])])
    vp.plan(None, None, CourseBrief(title="t"), video(), [scene()], [obj()],
            client=client)
    assert client.messages.calls[0]["model"] == settings().models.mid


def test_the_template_catalogue_reaches_the_model():
    client = FakeClient([plan_json([entry()])])
    vp.plan(None, None, CourseBrief(title="t"), video(), [scene()], [obj()],
            client=client)
    sent = client.messages.calls[0]["messages"][0]["content"]
    for name in ("state_timeline", "key_phrase", "table_build"):
        assert name in sent
    # ISSUE-20: an undesigned template must not reach the model at all — the
    # model cannot choose what it is not shown.
    for undesigned in ("labelled_diagram", "terminal_replay", "ui_walkthrough"):
        assert undesigned not in sent


# ============ ISSUE-21: resolution_state, a SCENE property not a cue kind

def test_resolution_state_is_required_and_validated():
    """A cue is an EVENT anchored to a span at a moment. "This scene shows the
    broken state" is a property of the whole scene; encoding it as a point
    event would be the wrong shape, and would add a fifth kind to §9.2's fixed
    list of four."""
    with pytest.raises(vp.ox.SchemaError) as e:
        vp.parse(plan_json([entry(state="green")]), [scene()])
    assert "resolution_state" in str(e.value)


def test_the_four_states_are_the_ones_grounded_in_section_3():
    assert vp.RESOLUTION_STATES == ("neutral", "broken", "caution", "resolved")


def test_signal_is_not_a_scene_state():
    """§3's `signal` means "currently being discussed" and stays a CUE-level
    role. Every scene is being discussed, so it is not a state a scene can be
    in."""
    assert "signal" not in vp.RESOLUTION_STATES


def test_the_state_reaches_the_visual_spec():
    plans = vp.parse(plan_json([entry(state="resolved")]), [scene()])
    spec = plans[0].visual_spec({})
    assert spec["resolution_state"] == "resolved"


def test_the_state_is_a_named_overridable_decision():
    """§10: every AI decision is a named, addressable, overridable object."""
    plans = vp.parse(plan_json([entry(state="broken")]), [scene()])
    d = plans[0].visual_spec({})["decisions"]
    assert d["resolution_state"]["value"] == "broken"
    assert "ISSUE-21" in d["resolution_state"]["rule"]


def test_every_state_survives_a_round_trip():
    for st in vp.RESOLUTION_STATES:
        plans = vp.parse(plan_json([entry(state=st)]), [scene()])
        assert plans[0].resolution_state == st

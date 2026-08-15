"""Signal designer — §8, §9.2 Signalling, CHALLENGES R3.

The two blocking checks are set membership: a cue's span must exist in this
scene, and its target must exist in this template. Both are testable without a
model, and both are the difference between a cue that fires and one that refers
to nothing.
"""
from __future__ import annotations

import json

import pytest

from explainer.agents import signal_designer as sd
from explainer.spans import Narration
from tests.test_objective_extraction import FakeClient

TEXT = ("The old version keeps its xmin. A new version gets xmin 105. "
        "Your snapshot decides which one you see.")


def narration() -> Narration:
    return Narration.author(TEXT)


def scene(ref="s01", template="labelled_diagram", slots=None, narr=None):
    return {
        "ref": ref, "gagne_slot": "present",
        "narration": narr or narration(),
        "visual_spec": {
            "template": template,
            "slots": slots if slots is not None else {
                "nodes": [{"id": "old", "label": "old version"},
                          {"id": "new", "label": "new version"}],
                "focus": "new"},
        },
    }


def cue(span_id, target="nodes.old", kind="highlight", point="start",
        offset_ms=-80, rationale="r"):
    return {"kind": kind, "target": target, "span_id": span_id, "point": point,
            "offset_ms": offset_ms, "rationale": rationale}


def plan_json(entries):
    return json.dumps({"scenes": entries})


def run(cues, scenes=None):
    scenes = scenes or [scene()]
    entries = [{"scene_ref": scenes[0]["ref"], "cues": cues}]
    client = FakeClient([plan_json(entries)])
    return sd.design(None, None, {"ref": "v2"}, scenes, client=client)


# --------------------------------------------------------------- R3

def test_a_cue_anchors_to_a_span_never_a_timestamp():
    """R3 is enforced by the type: spans.Anchor has no timestamp field."""
    from explainer.spans import Anchor
    assert not hasattr(Anchor("sp_x"), "timestamp")
    assert "spanId" in Anchor("sp_x").to_json()
    assert "time" not in json.dumps(Anchor("sp_x").to_json()).lower()


def test_a_cue_pointing_at_a_missing_span_is_blocking():
    n = narration()
    problems = sd.check_span("s01", "sp_deadbeef00", n)
    assert problems and "not in this scene's narration" in problems[0]


def test_a_cue_pointing_at_a_real_span_passes():
    n = narration()
    assert not sd.check_span("s01", n.spans[0].id, n)


def test_the_error_lists_the_spans_that_do_exist():
    """A human debugging this needs the candidates, not just the failure."""
    n = narration()
    problems = sd.check_span("s01", "sp_0000000000", n)
    assert n.spans[0].id in problems[0]


def test_offsets_are_stored_as_rational_time_at_millisecond_rate():
    """R2: no rounding at the boundary — 1000 ticks/s makes a ms exact."""
    n = narration()
    p = run([cue(n.spans[0].id, offset_ms=-120)], [scene(narr=n)])
    anchor = p.scenes[0].cues[0].anchor
    assert anchor.offset.rate == 1000
    assert anchor.offset.value == -120


# ------------------------------------------------------- target checking

def test_a_target_naming_a_slot_the_template_lacks_is_blocking():
    from explainer import templates
    problems = sd.check_target("s01", "captions", templates.get("labelled_diagram"),
                               {"nodes": []})
    assert problems and "does not have" in problems[0]


def test_a_target_naming_an_unfilled_slot_is_blocking():
    from explainer import templates
    problems = sd.check_target("s01", "edges", templates.get("labelled_diagram"),
                               {"nodes": []})
    assert problems and "nothing on screen to affect" in problems[0]


def test_a_target_indexing_past_the_end_is_blocking():
    from explainer import templates
    problems = sd.check_target("s01", "nodes[5]", templates.get("labelled_diagram"),
                               {"nodes": [{"id": "a", "label": "a"}]})
    assert problems and "indexes item 5" in problems[0]


def test_a_valid_target_passes_in_all_three_forms():
    from explainer import templates
    t = templates.get("labelled_diagram")
    slots = {"nodes": [{"id": "old", "label": "old"}], "focus": "old"}
    assert not sd.check_target("s01", "nodes", t, slots)
    assert not sd.check_target("s01", "nodes.old", t, slots)
    assert not sd.check_target("s01", "nodes[0]", t, slots)


def test_a_malformed_target_is_reported():
    from explainer import templates
    problems = sd.check_target("s01", "nodes..old", templates.get("labelled_diagram"),
                               {"nodes": []})
    assert problems


# ------------------------------------------------------- §9.2 the numbers

def test_the_permitted_kinds_are_exactly_the_four_in_the_spec():
    assert sd.CUE_KINDS == ("highlight", "pointer", "scale_pulse", "dim")


def test_the_spec_numbers_are_transcribed():
    """Guards the transcription: if someone 'tunes' one, the spec and the code
    have silently diverged."""
    assert sd.MAX_OFFSET_MS == 150
    assert sd.SCALE_PULSE_MAX == 1.20
    assert sd.SCALE_PULSE_MAX_MS == 400
    assert sd.DIM_OPACITY == 0.40
    assert (sd.MIN_CUES_PER_SCENE, sd.MAX_CUES_PER_SCENE) == (1, 3)


def test_an_offset_beyond_the_tolerance_is_rejected():
    assert sd.check_offset("s01", 400)
    assert sd.check_offset("s01", -400)


def test_an_offset_inside_the_tolerance_passes():
    assert not sd.check_offset("s01", -150)
    assert not sd.check_offset("s01", 0)
    assert not sd.check_offset("s01", 150)


def test_zero_cues_on_a_signalling_template_is_rejected():
    """§9.2: 'Never zero.'"""
    from explainer import templates
    problems = sd.check_count("s01", 0, templates.get("labelled_diagram"))
    assert problems and "never zero" in problems[0]


def test_more_than_three_cues_is_rejected():
    from explainer import templates
    problems = sd.check_count("s01", 4, templates.get("labelled_diagram"))
    assert problems and "maximum of 3" in problems[0]


def test_every_template_must_now_carry_a_cue():
    """ISSUE-13: the exemption is gone. §9.2's 'never zero' applies to
    key_phrase exactly as it applies to labelled_diagram."""
    from explainer import templates
    assert sd.check_count("s01", 0, templates.get("key_phrase"))
    assert not sd.check_count("s01", 1, templates.get("key_phrase"))


def test_scale_pulse_carries_its_spec_bounds_without_being_asked():
    n = narration()
    p = run([cue(n.spans[0].id, kind="scale_pulse")], [scene(narr=n)])
    params = p.scenes[0].cues[0].params
    assert params["max_scale"] == sd.SCALE_PULSE_MAX
    assert params["max_ms"] == sd.SCALE_PULSE_MAX_MS


def test_dim_carries_its_spec_opacity():
    n = narration()
    p = run([cue(n.spans[0].id, kind="dim")], [scene(narr=n)])
    assert p.scenes[0].cues[0].params["non_focal_opacity"] == sd.DIM_OPACITY


def test_an_unpermitted_kind_is_rejected():
    n = narration()
    with pytest.raises(sd.ox.SchemaError) as e:
        sd.parse(plan_json([{"scene_ref": "s01",
                             "cues": [cue(n.spans[0].id, kind="wiggle")]}]),
                 [scene(narr=n)])
    assert "permitted signals" in str(e.value)


# ------------------------------------------------------------ end to end

def test_a_valid_plan_produces_cues_and_provenance():
    n = narration()
    p = run([cue(n.spans[0].id), cue(n.spans[1].id, target="nodes.new")],
            [scene(narr=n)])
    assert p.cue_count == 2
    assert p.provenance["agent"] == "signal_designer"
    assert p.provenance["prompt_version"].startswith("signal_designer@v")


def test_a_bad_cue_goes_back_through_the_repair_loop():
    n = narration()
    bad = [{"scene_ref": "s01", "cues": [cue("sp_0000000000")]}]
    good = [{"scene_ref": "s01", "cues": [cue(n.spans[0].id)]}]
    client = FakeClient([plan_json(bad), plan_json(good)])
    p = sd.design(None, None, {"ref": "v2"}, [scene(narr=n)], client=client)
    assert len(p.attempts) == 2
    assert "not in this scene's narration" in p.attempts[0].error


def test_every_scene_needs_a_plan():
    n = narration()
    with pytest.raises(sd.ox.SchemaError) as e:
        sd.parse(plan_json([{"scene_ref": "s01", "cues": [cue(n.spans[0].id)]}]),
                 [scene("s01", narr=n), scene("s02", narr=n)])
    assert "no signal plan" in str(e.value) and "s02" in str(e.value)


def test_cue_json_round_trips_through_the_span_shape():
    n = narration()
    p = run([cue(n.spans[0].id)], [scene(narr=n)])
    payload = p.scenes[0].to_json()[0]
    assert payload["anchor"]["spanId"] == n.spans[0].id
    assert set(payload) == {"kind", "target", "anchor", "params"}


def test_the_spans_reach_the_model_with_their_ids():
    n = narration()
    client = FakeClient([plan_json([{"scene_ref": "s01",
                                     "cues": [cue(n.spans[0].id)]}])])
    sd.design(None, None, {"ref": "v2"}, [scene(narr=n)], client=client)
    sent = client.messages.calls[0]["messages"][0]["content"]
    for sp in n.spans:
        assert sp.id in sent, "the model cannot anchor to a span it cannot see"

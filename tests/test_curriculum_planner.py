"""Curriculum planner — §6 Stage 2b, §8, §5.3.

These test the two things the planner is not allowed to get wrong: the
two-objective cap and the prerequisite ordering. Both are hard errors in code,
not model judgment, so they are testable without a model call.
"""
from __future__ import annotations

import json

import pytest

from explainer.agents import curriculum_planner as cp
from explainer.brief import CourseBrief
from explainer.objectives import Bloom, KnowledgeType, Objective
from tests.test_objective_extraction import FakeClient


def obj(ref, bloom=Bloom.APPLY, ktype="conceptual", prereqs=(), assumed=False):
    return Objective(ref=ref, verb="predict", object=f"thing {ref}",
                     bloom_level=bloom, knowledge_type=KnowledgeType(ktype),
                     prerequisites=list(prereqs), assumed=assumed)


def brief(max_videos=1, seconds=300):
    return CourseBrief(title="MVCC and write skew", max_videos=max_videos,
                       target_seconds_per_video=seconds)


def plan_json(videos, notes=""):
    return json.dumps({"videos": videos, "notes": notes})


# ------------------------------------------------------------ script type

def test_conceptual_maps_to_explainer():
    assert cp.script_type_for([obj("o1", Bloom.APPLY, "conceptual")]) == "explainer"


def test_analyze_conceptual_maps_to_compare_contrast():
    """§8 says conceptual -> 'Explainer/Compare'; §9.1's Bloom table breaks the
    tie by putting compare/contrast at Analyze."""
    assert cp.script_type_for([obj("o1", Bloom.ANALYZE, "conceptual")]) == "compare_contrast"


def test_procedural_maps_to_procedure_demo():
    assert cp.script_type_for([obj("o1", Bloom.APPLY, "procedural")]) == "procedure_demo"


def test_the_most_demanding_objective_drives_the_script_type():
    objs = [obj("o1", Bloom.REMEMBER, "conceptual"), obj("o2", Bloom.ANALYZE, "conceptual")]
    assert cp.script_type_for(objs) == "compare_contrast"


@pytest.mark.parametrize("ktype", ["factual", "metacognitive"])
def test_uncovered_knowledge_types_raise_rather_than_guess(ktype):
    """§8's table states procedural and conceptual only. A branch no data
    covers must not get an invented mapping that later reads as spec."""
    with pytest.raises(NotImplementedError) as e:
        cp.script_type_for([obj("o1", Bloom.APPLY, ktype)])
    assert "§8" in str(e.value) and ktype in str(e.value)


# -------------------------------------------------------- structural gates

def test_three_objectives_in_one_video_is_a_hard_error():
    objs = [obj("o1"), obj("o2"), obj("o3")]
    videos = [cp.PlannedVideo(ref="v1", title="t", objective_refs=["o1", "o2", "o3"])]
    with pytest.raises(cp.PlanError) as e:
        cp.check_plan(videos, objs, ["o1", "o2", "o3"])
    assert "at most 2" in str(e.value)


def test_forward_dependency_is_a_hard_error():
    """A video may not depend on an objective a later video teaches."""
    objs = [obj("o1", prereqs=["o2"]), obj("o2")]
    videos = [cp.PlannedVideo(ref="v1", title="a", objective_refs=["o1"], ordinal=1),
              cp.PlannedVideo(ref="v2", title="b", objective_refs=["o2"], ordinal=2)]
    with pytest.raises(cp.PlanError) as e:
        cp.check_plan(videos, objs, ["o2", "o1"])
    assert "taught later" in str(e.value)


def test_an_unplaced_taught_objective_is_a_hard_error():
    objs = [obj("o1"), obj("o2")]
    videos = [cp.PlannedVideo(ref="v1", title="t", objective_refs=["o1"])]
    with pytest.raises(cp.PlanError) as e:
        cp.check_plan(videos, objs, ["o1", "o2"])
    assert "not placed" in str(e.value)


def test_an_assumed_objective_may_not_carry_a_video():
    objs = [obj("o1"), obj("a1", assumed=True)]
    videos = [cp.PlannedVideo(ref="v1", title="t", objective_refs=["o1"]),
              cp.PlannedVideo(ref="v2", title="t", objective_refs=["a1"])]
    with pytest.raises(cp.PlanError) as e:
        cp.check_plan(videos, objs, ["a1", "o1"])
    assert "assumed" in str(e.value)


def test_an_objective_in_two_videos_is_a_hard_error():
    objs = [obj("o1"), obj("o2")]
    videos = [cp.PlannedVideo(ref="v1", title="t", objective_refs=["o1", "o2"]),
              cp.PlannedVideo(ref="v2", title="t", objective_refs=["o1"])]
    with pytest.raises(cp.PlanError) as e:
        cp.check_plan(videos, objs, ["o1", "o2"])
    assert "more than one video" in str(e.value)


def test_a_valid_plan_passes():
    objs = [obj("a1", assumed=True), obj("o1"), obj("o2", prereqs=["o1"])]
    videos = [cp.PlannedVideo(ref="v1", title="t", objective_refs=["o1", "o2"],
                              ordinal=1)]
    cp.check_plan(videos, objs, ["a1", "o1", "o2"])       # must not raise


# ------------------------------------------------------------ acceptance

def test_max_videos_one_two_objectives_yields_exactly_one_video():
    """The acceptance criterion: max_videos=1 with 2 taught objectives emits one
    video covering both."""
    objs = [obj("a1", assumed=True),
            obj("o1", Bloom.APPLY, "conceptual"),
            obj("o2", Bloom.APPLY, "conceptual", prereqs=["o1"])]
    client = FakeClient([plan_json([{
        "ref": "v1", "title": "When Repeatable Read isn't enough",
        "objective_refs": ["o1", "o2"],
        "rationale": "the second is the immediate consequence of the first",
    }])])
    result = cp.plan(None, None, brief(max_videos=1), objs, ["a1", "o1", "o2"],
                     client=client)
    assert len(result.videos) == 1
    assert result.videos[0].objective_refs == ["o1", "o2"]
    assert result.videos[0].script_type == "explainer"
    assert result.videos[0].target_seconds == 300


def test_target_seconds_is_capped_at_the_six_minute_hard_cap():
    """§9.2 Segmenting: hard cap 6:00."""
    objs = [obj("o1")]
    client = FakeClient([plan_json([{"ref": "v1", "title": "t",
                                     "objective_refs": ["o1"], "rationale": ""}])])
    result = cp.plan(None, None, brief(seconds=900), objs, ["o1"], client=client)
    assert result.videos[0].target_seconds == cp.HARD_CAP_SECONDS


def test_a_bad_plan_raises_and_is_not_silently_repaired():
    """Structural failures are not schema failures — no repair round trip."""
    objs = [obj("o1"), obj("o2"), obj("o3")]
    client = FakeClient([plan_json([{
        "ref": "v1", "title": "t", "objective_refs": ["o1", "o2", "o3"],
        "rationale": ""}])])
    with pytest.raises(cp.PlanError):
        cp.plan(None, None, brief(), objs, ["o1", "o2", "o3"], client=client)
    assert len(client.messages.calls) == 1, "no repair attempt for a structural error"


def test_schema_failure_does_get_a_repair_round_trip():
    objs = [obj("o1")]
    good = plan_json([{"ref": "v1", "title": "t", "objective_refs": ["o1"],
                       "rationale": ""}])
    client = FakeClient(["not json", good])
    result = cp.plan(None, None, brief(), objs, ["o1"], client=client)
    assert len(result.attempts) == 2
    assert result.provenance["attempt"] == 2


def test_the_pinned_mid_tier_model_is_used():
    from explainer.config import settings
    objs = [obj("o1")]
    client = FakeClient([plan_json([{"ref": "v1", "title": "t",
                                     "objective_refs": ["o1"], "rationale": ""}])])
    cp.plan(None, None, brief(), objs, ["o1"], client=client)
    assert client.messages.calls[0]["model"] == settings().models.mid

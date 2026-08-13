"""DAG shape tests — no database required."""
import pytest

from explainer.dag import (BeatRef, Dep, DepKind, Graph, Node, Pool, Scope,
                           StageSpec, dependencies, expand, topological_stages)
from explainer.graphs.fake import GRAPH as FAKE
from explainer.graphs.production import GRAPH as PROD

BEATS = [BeatRef(f"b{i:02d}", i, {"text": f"t{i}"}) for i in range(1, 6)]


def test_fake_graph_orders_stages():
    assert FAKE.order == ["research", "script", "tts", "pacing", "assembly"]


def test_production_graph_is_acyclic_and_complete():
    assert len(PROD.order) == len(PROD.stages)
    assert PROD.order[0] == "research"
    assert PROD.terminal == "finishing"


def test_cycle_is_rejected():
    stages = {
        "a": StageSpec("a", Scope.VIDEO, Pool.AGENT, deps=(Dep("b", DepKind.VIDEO),)),
        "b": StageSpec("b", Scope.VIDEO, Pool.AGENT, deps=(Dep("a", DepKind.VIDEO),)),
    }
    with pytest.raises(ValueError, match="cycle"):
        topological_stages(stages)


def test_self_dependency_is_rejected():
    stages = {"a": StageSpec("a", Scope.VIDEO, Pool.AGENT, deps=(Dep("a", DepKind.VIDEO),))}
    with pytest.raises(ValueError, match="itself"):
        topological_stages(stages)


def test_expansion_counts():
    nodes = expand(FAKE, BEATS)
    assert len(nodes) == 1 + 3 * len(BEATS) + 1
    assert nodes[0].key == "research"
    assert nodes[-1].key == "assembly"


def test_upto_prunes_downstream_stages():
    assert FAKE.upto("tts") == ["research", "script", "tts"]


def test_same_beat_dependency():
    deps = dependencies(FAKE, Node("tts", "b03", 3), BEATS)
    assert deps == {"script": Node("script", "b03", 3)}


def test_neighbour_window_at_the_middle():
    deps = dependencies(FAKE, Node("pacing", "b03", 3), BEATS)
    assert set(deps) == {"tts:prev1", "tts:self", "tts:next1"}
    assert deps["tts:prev1"].beat_id == "b02"
    assert deps["tts:next1"].beat_id == "b04"


def test_neighbour_window_at_the_edges():
    first = dependencies(FAKE, Node("pacing", "b01", 1), BEATS)
    last = dependencies(FAKE, Node("pacing", "b05", 5), BEATS)
    assert set(first) == {"tts:self", "tts:next1"}
    assert set(last) == {"tts:prev1", "tts:self"}


def test_all_beats_dependency_covers_every_beat():
    deps = dependencies(FAKE, Node("assembly", None), BEATS)
    assert set(deps) == {f"pacing:{b.beat_id}" for b in BEATS}


def test_brand_only_touches_visual_stages():
    """Why a brand sweep is cheap (§5.4): brand is not an input to research,
    script or TTS, so bumping it cannot invalidate them."""
    brandful = {k for k, s in PROD.stages.items() if "brand_version" in s.config_keys}
    assert brandful == {"storyboard", "visual_critic", "render", "sound_design", "finishing"}


def test_beat_scoped_stages_are_where_the_granularity_is():
    beat_stages = {k for k, s in PROD.stages.items() if s.scope is Scope.BEAT}
    assert beat_stages == {"script_beat", "storyboard", "visual_critic", "tts",
                           "render", "pacing"}

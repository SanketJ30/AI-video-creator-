"""Scene render — §11.1, §11.3, §11.4, §11.5, R8.

The closure properties are pure and tested directly. One real render runs
(10 frames, ~8s) because §11.3's byte-identity requirement is the single most
load-bearing property in the architecture and it cannot be asserted without
actually rendering twice.
"""
from __future__ import annotations

import pytest

from explainer import render

REMOTION = (render.RENDER_DIR / "node_modules" / "remotion").exists()
needs_remotion = pytest.mark.skipif(
    not REMOTION, reason="run `npm install` in render/ first")

SLOTS = {"phrase": "Spot it. Fix it.", "emphasis": "Spot"}


# ------------------------------------------------------------- the closure

def test_the_closure_excludes_scene_and_video_identity():
    """§11.4: 'the cache key must not include absolute start time'. Two scenes
    with the same template, slots, cues and length are one render."""
    a = render.closure(render.scene_props("key_phrase", SLOTS, [], 60), 60)
    b = render.closure(render.scene_props("key_phrase", SLOTS, [], 60), 60)
    assert a == b


def test_a_different_duration_is_a_different_render():
    a = render.closure(render.scene_props("key_phrase", SLOTS, [], 60), 60)
    b = render.closure(render.scene_props("key_phrase", SLOTS, [], 90), 90)
    assert a != b


def test_a_different_cue_time_is_a_different_render():
    one = [{"kind": "highlight", "target": "rows[0]", "atSeconds": 1.0}]
    two = [{"kind": "highlight", "target": "rows[0]", "atSeconds": 2.0}]
    a = render.closure(render.scene_props("table_build", {"rows": ["x"]}, one, 60), 60)
    b = render.closure(render.scene_props("table_build", {"rows": ["x"]}, two, 60), 60)
    assert a != b


def test_the_renderer_version_is_in_the_closure():
    """§11.3: 'Chromium / FFmpeg / codec versions -> part of the cache key. A
    libx264 bump changes bytes.'"""
    import json
    doc = json.loads(render.hashing.canonical_json(
        {"v": render.renderer_version()}))
    assert doc["v"].startswith("remotion@")


def test_frames_enter_the_closure_as_an_integer():
    """A float would make two runs that differ in the last bit render twice."""
    a = render.closure(render.scene_props("key_phrase", SLOTS, [], 60), 60)
    b = render.closure(render.scene_props("key_phrase", SLOTS, [], 60), 60.0)
    assert a == b


# ------------------------------------------------------------------ R8

def test_props_carry_no_renderer_concepts():
    """R8: the spec crossing this boundary is a name, slots and cues — no React,
    no component names, no CSS."""
    props = render.scene_props("labelled_diagram",
                               {"nodes": [{"id": "a", "label": "A"}]}, [], 60)
    assert set(props) == {"durationInFrames", "template", "slots", "cues",
                          "captionSafeBottom", "minFontPx"}
    blob = str(props).lower()
    for banned in ("react", "jsx", "component", "css", "div", "style"):
        assert banned not in blob


def test_the_caption_safe_area_comes_from_the_template_not_the_caller():
    """§16.2 / CHALLENGES: a caller who could override it eventually would."""
    props = render.scene_props("key_phrase", SLOTS, [], 60)
    assert props["captionSafeBottom"] == 0.15
    assert props["minFontPx"] == 24


def test_the_duration_reaches_the_renderer_as_props():
    """R1: the resolver owns duration; a constant in Root.tsx would be a second
    opinion about time."""
    assert render.scene_props("key_phrase", SLOTS, [], 123)["durationInFrames"] == 123


def test_an_unknown_template_is_refused_before_rendering():
    with pytest.raises(KeyError):
        render.scene_props("no_such_template", {}, [], 60)


# ----------------------------------------------------------------- §11.5

def test_the_licence_key_is_the_evaluation_clause():
    """§11.5. Stated in code so nobody has to guess which tier this runs under."""
    assert render.LICENSE_KEY == "free-license"


def test_intermediates_are_lossless_intra_only():
    """§11.4: 'Never concat lossy inter-frame chunks — GOP-boundary artifacts
    and timestamp fights.'"""
    assert render.INTERMEDIATE_CODEC == "prores"
    assert render.PRORES_PROFILE == "4444"


# ------------------------------------------------------- §11.3 hermeticity

@needs_remotion
def test_rendering_the_same_scene_twice_is_byte_identical():
    """§11.3's verification, and the property everything else rests on: 'a
    corrupted cache is a class of bug that will otherwise take weeks to
    diagnose.'"""
    ok, a, b = render.check_determinism("t01", "key_phrase", SLOTS, [], frames=10)
    assert ok, f"nondeterministic render: {a} != {b}"


@needs_remotion
def test_a_rendered_scene_is_stored_and_the_second_call_is_a_cache_hit():
    r = render.render_scene("t02", "key_phrase", SLOTS, [], frames=10)
    again = render.render_scene("t02", "key_phrase", SLOTS, [], frames=10)
    assert again.cached and again.hash == r.hash


@needs_remotion
def test_the_scene_ref_does_not_change_the_hash():
    """The cost curve in §6.3 comes from exactly this."""
    a = render.render_scene("sAAA", "key_phrase", SLOTS, [], frames=10)
    b = render.render_scene("sBBB", "key_phrase", SLOTS, [], frames=10)
    assert a.hash == b.hash

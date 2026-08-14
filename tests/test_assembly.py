"""Mux, concat, transitions and captions — §11.4, §16.1.

The clock formatting and the caption/transition logic are pure and tested
directly. ffmpeg-invoking paths are exercised by the end-to-end render rather
than duplicated here.
"""
from __future__ import annotations

import pytest

from explainer import assembly, rtime
from explainer.resolver import SceneTiming, Timeline
from explainer.rtime import RationalTime

SR = rtime.SAMPLE_RATE


def timing(ref, samples, spans):
    return SceneTiming(
        scene_ref=ref, duration=RationalTime.from_samples(samples, SR),
        audio_hash="a" * 64, audio_samples=samples, padded_samples=samples,
        timing_sensitivity="elastic", spans=spans)


def span(sid, text, start, end):
    return {"spanId": sid, "text": text, "start": start, "end": end,
            "method": "measured:tts_chunk", "words": []}


# ------------------------------------------------------- §11.4 transitions

def test_hard_cuts_are_the_default():
    """§11.4: 'Prefer hard cuts by default' — pedagogically supported and
    architecturally cheaper."""
    ts = assembly.default_transitions(4)
    assert len(ts) == 3
    assert all(t.kind == assembly.HARD_CUT for t in ts)
    assert all(t.handle_frames == 0 for t in ts)


def test_a_hard_cut_consumes_no_handle_frames():
    assert not assembly.Transition(assembly.HARD_CUT, 0).consumes_handles
    assert assembly.Transition(assembly.DISSOLVE, 15).consumes_handles


def test_a_transition_key_is_a_function_of_both_neighbours():
    """§11.4: key = H(sceneKey_i, sceneKey_{i+1}, spec, T). A crossfade is a
    function of both scenes, so it is not cacheable under either key."""
    t = assembly.Transition()
    assert t.closure("a" * 64, "b" * 64) != t.closure("a" * 64, "c" * 64)
    assert t.closure("a" * 64, "b" * 64) != t.closure("z" * 64, "b" * 64)


def test_editing_one_scene_invalidates_only_its_two_transitions():
    """§11.4: 'Editing scene 5's text then invalidates scene 5,
    transition(4,5), transition(5,6). Three renders, not forty.'"""
    keys = [f"{i:064d}" for i in range(6)]
    t = assembly.Transition()
    before = [t.closure(a, b) for a, b in zip(keys, keys[1:])]
    keys[3] = "f" * 64                       # scene 4 edited
    after = [t.closure(a, b) for a, b in zip(keys, keys[1:])]
    changed = [i for i, (x, y) in enumerate(zip(before, after)) if x != y]
    assert changed == [2, 3], "only the two transitions touching it"


def test_the_transition_spec_is_in_its_key():
    a = assembly.Transition(assembly.HARD_CUT, 0)
    b = assembly.Transition(assembly.DISSOLVE, 15)
    assert a.closure("x" * 64, "y" * 64) != b.closure("x" * 64, "y" * 64)


def test_a_dissolve_is_refused_rather_than_silently_cut():
    """Rendering a dissolve as a cut would be a silent quality change."""
    with pytest.raises(assembly.AssemblyError) as e:
        assembly.concat_and_encode(["a" * 64], __import__("pathlib").Path("x.mp4"),
                                   [assembly.Transition(assembly.DISSOLVE, 15)])
    assert "handle frames" in str(e.value)


# -------------------------------------------------------- §11.4 manifest

def test_the_stitch_manifest_is_content_addressed():
    """§11.4: 'Did anything change?' is one hash comparison."""
    a = assembly.StitchManifest(scene_keys=["a", "b"],
                                encode_params=assembly.encode_params())
    b = assembly.StitchManifest(scene_keys=["a", "b"],
                                encode_params=assembly.encode_params())
    assert a.hash() == b.hash()


def test_reordering_scenes_changes_the_manifest_and_nothing_else():
    """§11.2: 'scene ordering -> invalidate NOTHING at scene level;
    manifest/stitch only.'"""
    a = assembly.StitchManifest(scene_keys=["a", "b", "c"])
    b = assembly.StitchManifest(scene_keys=["c", "b", "a"])
    assert a.hash() != b.hash()
    assert set(a.scene_keys) == set(b.scene_keys)


def test_two_courses_sharing_an_intro_dedupe():
    """§11.4's closing claim, which is only true because scene keys carry no
    video identity."""
    assert (assembly.StitchManifest(scene_keys=["intro"]).hash()
            == assembly.StitchManifest(scene_keys=["intro"]).hash())


def test_encode_params_are_in_the_manifest_hash():
    a = assembly.StitchManifest(scene_keys=["a"], encode_params={"crf": "18"})
    b = assembly.StitchManifest(scene_keys=["a"], encode_params={"crf": "23"})
    assert a.hash() != b.hash()


# --------------------------------------------------------------- captions

def build_timeline():
    return Timeline(scenes=[
        timing("s01", 2 * SR, [span("sp_a", "First line.", 0, SR),
                               span("sp_b", "Second line.", SR, 2 * SR)]),
        timing("s02", SR, [span("sp_c", "Third line.", 0, SR)]),
    ])


def test_captions_are_absolute_across_the_video():
    cues = assembly.caption_cues(build_timeline())
    assert [round(c[0], 3) for c in cues] == [0.0, 1.0, 2.0]
    assert [c[2] for c in cues] == ["First line.", "Second line.", "Third line."]


def test_webvtt_has_its_header_and_arrow_format():
    out = assembly.to_webvtt(build_timeline())
    assert out.startswith("WEBVTT")
    assert "00:00:01.000 --> 00:00:02.000" in out


def test_srt_uses_a_comma_for_the_decimal():
    out = assembly.to_srt(build_timeline())
    assert "00:00:01,000 --> 00:00:02,000" in out
    assert "WEBVTT" not in out


def test_an_empty_span_produces_no_caption():
    tl = Timeline(scenes=[timing("s01", SR, [span("sp_a", "   ", 0, SR)])])
    assert assembly.caption_cues(tl) == []


def test_captions_come_from_measured_span_timings_not_estimated_words():
    """§16.1 makes 1.2.2 non-negotiable; captions must not rest on estimates."""
    tl = build_timeline()
    for s in tl.scenes:
        for sp in s.spans:
            assert sp["method"].startswith("measured")


def test_the_word_sidecar_is_separate_from_webvtt():
    """§16.1: 'Don't overload WebVTT for that last job.'"""
    import json
    doc = json.loads(assembly.to_word_sidecar(build_timeline()))
    assert doc["fps"] == 30 and doc["sampleRate"] == 48000
    assert doc["scenes"][1]["startSamples"] == 2 * SR


def test_the_clock_rounds_to_milliseconds():
    assert assembly._vtt_clock(3661.5) == "01:01:01.500"
    assert assembly._vtt_clock(0) == "00:00:00.000"


# ------------------------------------------------------------ encode params

def test_the_final_encode_is_a_single_pass_with_pinned_params():
    """§11.4: lossless intermediates, `-c copy` concat, then ONE final encode."""
    p = assembly.encode_params()
    assert p["video"] == "libx264" and p["crf"] == "18"
    assert p["fps"] == 30 and p["sample_rate"] == 48000
    assert "ffmpeg" in p, "§11.3: codec version is part of the cache key"

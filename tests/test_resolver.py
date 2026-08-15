"""The two-phase timing resolver — §11.2, §11.4, §15.3, R1/R2/R5.

Fixtures are built from fake audio with exact sample counts so every assertion
is arithmetic rather than a property of whatever the TTS happened to produce.
The one thing that must never be fudged is the frame alignment: §11.4's whole
sample-accurate-concat argument rests on integer frame counts.
"""
from __future__ import annotations

import pytest

from explainer import resolver, rtime
from explainer.align import SceneAlignment, SpanTiming

SR = rtime.SAMPLE_RATE          # 48000
FRAME = rtime.SAMPLES_PER_FRAME  # 1600


class FakeAudio:
    def __init__(self, samples: int):
        self.sample_count = samples
        self.hash = "a" * 64
        self.sample_rate = SR
        self.chunks = [{"start": 0, "end": samples}]


class FakeSpeech:
    def __init__(self, samples: int, spans=None, fallback=False):
        self.audio = FakeAudio(samples)
        self.per_span_fallback = fallback
        self.alignment = SceneAlignment(
            scene_ref="s01", audio_hash="a" * 64, sample_rate=SR,
            spans=spans or [SpanTiming(span_id="sp_one", text="one",
                                       start=0, end=samples)])


def scene(ref="s01", samples=SR, sensitivity="elastic", target=None, cues=None):
    return {"ref": ref, "speech": FakeSpeech(samples),
            "timing_sensitivity": sensitivity, "target_seconds": target,
            "cues": cues or []}


# ------------------------------------------------------- §11.4 frame counts

def test_every_duration_is_frame_aligned():
    """§11.4: 'Force integer frame counts for every scene duration.'"""
    tl = resolver.resolve([scene(samples=SR + 7), scene("s02", samples=12345)])
    for s in tl.scenes:
        assert s.duration.is_frame_aligned()
        assert s.padded_samples % FRAME == 0


def test_audio_is_padded_up_never_truncated():
    """Padding down would cut words off the end of a sentence."""
    tl = resolver.resolve([scene(samples=FRAME + 1)])
    s = tl.scenes[0]
    assert s.padded_samples == 2 * FRAME
    assert s.padded_samples > s.audio_samples
    assert s.silence_samples == FRAME - 1


def test_audio_already_on_a_frame_boundary_is_not_padded():
    tl = resolver.resolve([scene(samples=10 * FRAME)])
    assert tl.scenes[0].silence_samples == 0


def test_one_frame_is_exactly_1600_samples():
    """§11.4: '30 fps + 48 kHz = exactly 1600 samples/frame'. The whole
    sample-accurate story depends on this being exact, not rounded."""
    assert rtime.FPS == 30 and SR == 48000 and FRAME == 1600


def test_the_total_is_the_sum_with_no_drift():
    tl = resolver.resolve([scene(samples=n) for n in (SR, SR + 3, 2 * SR - 1)])
    assert tl.total_frames == sum(s.frames for s in tl.scenes)
    assert tl.total.is_frame_aligned()


# -------------------------------------------------------- R1: derived starts

def test_starts_are_derived_by_accumulation_not_stored():
    tl = resolver.resolve([scene("s01", samples=10 * FRAME),
                           scene("s02", samples=5 * FRAME),
                           scene("s03", samples=FRAME)])
    starts = tl.starts()
    assert starts["s01"].frames == 0
    assert starts["s02"].frames == 10
    assert starts["s03"].frames == 15


def test_a_scene_timing_carries_no_absolute_position():
    """§11.4: 'the cache key must not include absolute start time'. If a start
    were a field here it would eventually reach a hash."""
    s = resolver.resolve([scene()]).scenes[0]
    assert not hasattr(s, "start")
    assert "start" not in s.to_json()


def test_reordering_changes_starts_but_no_durations():
    """§11.2's other big win: 'scene ordering -> invalidate NOTHING at scene
    level; manifest/stitch only'."""
    a = resolver.resolve([scene("s01", samples=10 * FRAME),
                          scene("s02", samples=5 * FRAME)])
    b = resolver.resolve([scene("s02", samples=5 * FRAME),
                          scene("s01", samples=10 * FRAME)])
    da = {s.scene_ref: s.padded_samples for s in a.scenes}
    db = {s.scene_ref: s.padded_samples for s in b.scenes}
    assert da == db
    assert a.starts()["s01"].frames != b.starts()["s01"].frames


# ---------------------------------------------------- §15.3 rigid / elastic

def test_an_elastic_scene_derives_its_duration_from_the_audio():
    """R5 and §15.3 strategy A."""
    tl = resolver.resolve([scene(samples=7 * FRAME, sensitivity="elastic",
                                 target=60)])
    assert tl.scenes[0].frames == 7, "the 60s target must not win here"


def test_a_rigid_scene_keeps_its_authored_duration():
    tl = resolver.resolve([scene(samples=FRAME, sensitivity="rigid", target=2)])
    assert tl.scenes[0].duration.seconds == pytest.approx(2.0)


def test_a_rigid_scene_fits_its_audio_with_silence():
    tl = resolver.resolve([scene(samples=SR, sensitivity="rigid", target=2)])
    s = tl.scenes[0]
    assert s.audio_samples == SR
    assert s.silence_samples == SR
    assert s.padded_samples == 2 * SR


def test_a_rigid_scene_with_no_target_is_an_error():
    """Rigid means the visual owns the tempo; without a target there is nothing
    to be rigid about."""
    with pytest.raises(resolver.ResolveError):
        resolver.resolve([scene(sensitivity="rigid", target=None)])


def test_excessive_silence_padding_is_reported():
    """§15.3 budgets ~15%. 1s of audio in a 10s rigid scene is 90%."""
    tl = resolver.resolve([scene(samples=SR, sensitivity="rigid", target=10)])
    assert any(p.kind == "excessive_padding" for p in tl.problems)


def test_padding_inside_the_budget_is_not_reported():
    tl = resolver.resolve([scene(samples=int(SR * 1.9), sensitivity="rigid",
                                 target=2)])
    assert not tl.problems


def test_a_rigid_overrun_is_reported_and_the_scene_is_left_long():
    """§15.3 forbids speeding TTS beyond +8%, and trimming would cut the end
    off a sentence. So the scene runs long and says so."""
    tl = resolver.resolve([scene(samples=5 * SR, sensitivity="rigid", target=2)])
    assert any(p.kind == "overrun" for p in tl.problems)
    assert tl.scenes[0].duration.seconds >= 5.0, "audio must not be truncated"


def test_the_fit_problem_names_the_scene_and_both_numbers():
    tl = resolver.resolve([scene("s04", samples=5 * SR, sensitivity="rigid",
                                 target=2)])
    text = str(tl.problems[0])
    assert "s04" in text and "5.00" in text and "2.00" in text


# ------------------------------------------------------------ R3: cue times

def two_span_speech():
    spans = [SpanTiming(span_id="sp_a", text="a", start=0, end=SR),
             SpanTiming(span_id="sp_b", text="b", start=SR, end=2 * SR)]
    return FakeSpeech(2 * SR, spans=spans)


def cue(span_id, offset_ms=0, point="start"):
    return {"kind": "highlight", "target": "nodes",
            "anchor": {"spanId": span_id, "point": point,
                       "offset": {"value": offset_ms, "rate": 1000}}}


def test_a_cue_resolves_from_its_span_to_a_local_time():
    tl = resolver.resolve([{"ref": "s01", "speech": two_span_speech(),
                            "timing_sensitivity": "elastic",
                            "cues": [cue("sp_b")]}])
    assert tl.scenes[0].cues[0].at.seconds == pytest.approx(1.0)


def test_a_cue_offset_shifts_it():
    tl = resolver.resolve([{"ref": "s01", "speech": two_span_speech(),
                            "timing_sensitivity": "elastic",
                            "cues": [cue("sp_b", offset_ms=-100)]}])
    assert tl.scenes[0].cues[0].at.seconds == pytest.approx(0.9)


def test_a_cue_anchored_to_a_span_end_resolves_there():
    tl = resolver.resolve([{"ref": "s01", "speech": two_span_speech(),
                            "timing_sensitivity": "elastic",
                            "cues": [cue("sp_a", point="end")]}])
    assert tl.scenes[0].cues[0].at.seconds == pytest.approx(1.0)


def test_a_negative_resolved_time_is_clamped_into_the_scene():
    """A cue at a negative time is not one that fires early — it is one that
    never fires."""
    tl = resolver.resolve([{"ref": "s01", "speech": two_span_speech(),
                            "timing_sensitivity": "elastic",
                            "cues": [cue("sp_a", offset_ms=-5000)]}])
    assert tl.scenes[0].cues[0].at.seconds == 0.0


def test_a_cue_naming_an_unknown_span_is_an_error():
    from explainer.align import AlignmentError
    with pytest.raises(AlignmentError):
        resolver.resolve([{"ref": "s01", "speech": two_span_speech(),
                           "timing_sensitivity": "elastic",
                           "cues": [cue("sp_nope")]}])


def test_cue_times_are_local_so_a_scene_render_is_position_independent():
    """§11.4. The same scene in a different slot resolves its cues identically."""
    first = resolver.resolve([{"ref": "s01", "speech": two_span_speech(),
                               "timing_sensitivity": "elastic",
                               "cues": [cue("sp_b")]}])
    later = resolver.resolve([scene("s00", samples=100 * FRAME),
                              {"ref": "s01", "speech": two_span_speech(),
                               "timing_sensitivity": "elastic",
                               "cues": [cue("sp_b")]}])
    assert (first.scenes[0].cues[0].at.seconds
            == later.scenes[1].cues[0].at.seconds)


# ------------------------------------------------------------------ output

def test_the_timeline_serialises_frames_and_seconds():
    doc = resolver.resolve([scene(samples=3 * FRAME)]).to_json()
    assert doc["fps"] == 30 and doc["sampleRate"] == 48000
    assert doc["scenes"][0]["durationFrames"] == 3
    assert doc["scenes"][0]["startFrames"] == 0


def test_the_per_span_fallback_is_carried_into_the_timeline():
    """ISSUE-11 must stay visible all the way to the manifest."""
    s = {"ref": "s05", "speech": FakeSpeech(SR, fallback=True),
         "timing_sensitivity": "elastic"}
    assert resolver.resolve([s]).scenes[0].per_span_fallback


# ==================================== ISSUE-14: where the silence sits

def test_padding_above_the_trailing_allowance_is_redistributed():
    """MEASURED on v2 s04: 10.91s of padding, ALL trailing, in the 90s scene
    carrying the whole explanation. §15.3's 15% budget is about absorbing
    contraction distributed across a scene, not one block at the end."""
    plan = resolver.distribute_padding(16, int(10.91 * SR), 90 * SR)
    assert plan.trailing == int(90 * SR * 0.04)
    assert len(plan.gaps) == 15
    assert all(g > 0 for g in plan.gaps)


def test_the_plan_preserves_every_sample():
    """A lost sample is a frame-alignment failure downstream."""
    total = int(10.91 * SR)
    assert resolver.distribute_padding(16, total, 90 * SR).total == total


def test_padding_inside_the_allowance_stays_trailing():
    """Below the threshold there is nothing to redistribute, and inserting
    beats anyway would add pauses nobody asked for."""
    plan = resolver.distribute_padding(8, SR, 100 * SR)
    assert plan.trailing == SR and not any(plan.gaps)


def test_a_single_span_scene_cannot_redistribute():
    """No boundary to put a beat at. The plan says so rather than the finished
    video saying it."""
    plan = resolver.distribute_padding(1, 5 * SR, 20 * SR)
    assert plan.gaps == [] and plan.trailing == 5 * SR


def test_no_padding_means_no_plan():
    assert resolver.distribute_padding(4, 0, 10 * SR).total == 0


def test_the_threshold_is_marked_authored():
    import inspect
    src = inspect.getsource(resolver)
    assert "AUTHORED AND UNREVIEWED" in src
    assert resolver.AUTHORED_MAX_TRAILING_SILENCE_SHARE == 0.04


def test_span_timings_shift_with_the_inserted_beats():
    """A cue resolved against unshifted timings fires while the previous span
    is still on screen, and the error grows with every gap."""
    from explainer.align import SceneAlignment, SpanTiming
    al = SceneAlignment(scene_ref="s01", audio_hash="a" * 64, sample_rate=SR,
                        spans=[SpanTiming("sp_a", "a", 0, SR),
                               SpanTiming("sp_b", "b", SR, 2 * SR),
                               SpanTiming("sp_c", "c", 2 * SR, 3 * SR)])
    resolver._apply_padding(al, resolver.PadPlan(gaps=[SR, SR], trailing=0))
    assert [(s.start, s.end) for s in al.spans] == [
        (0, SR), (2 * SR, 3 * SR), (4 * SR, 5 * SR)]


def test_a_rigid_scene_ends_with_at_most_the_allowed_tail():
    """The end-to-end property: no scene may finish on a long block of nothing."""
    spans = [SpanTiming(f"sp_{i}", "x", i * SR, (i + 1) * SR) for i in range(8)]
    sp = FakeSpeech(8 * SR, spans=spans)
    timing, _ = resolver.resolve_scene("s04", sp, "rigid", 20, [])
    allowed = timing.padded_samples * resolver.AUTHORED_MAX_TRAILING_SILENCE_SHARE
    assert timing.pad_plan.trailing <= allowed + 1
    assert sum(timing.pad_plan.gaps) > 0, "the rest must be spread, not dropped"

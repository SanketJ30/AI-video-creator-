"""Motion verbs, measured on rendered pixels — design system §10.

The point of this file: a motion system that produces no intermediate frames
must fail its own test.

That is not hypothetical. §10's grammar reached the token layer and the motion
module and was applied to **nothing**: `enter()` and `buildStep()` were defined
and never attached to an element's style, so every element appeared in a single
frame — absent, then present at full opacity. Measured on the finished video,
97.3% of frames were identical to the frame before them.

Every check here therefore renders real frames and measures the change between
them. Nothing is asserted about the source.
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest

from explainer import render

REMOTION = (render.RENDER_DIR / "node_modules" / "remotion").exists()
pytestmark = pytest.mark.skipif(
    not REMOTION, reason="run `npm install` in render/ first")

FPS = 30


def _frame_deltas(scene_hash: str, tmp: pathlib.Path) -> list[int]:
    """Changed pixels between consecutive frames, downscaled for speed."""
    from PIL import Image, ImageChops
    import imageio_ffmpeg

    src = tmp / "scene.mov"
    src.write_bytes(render.store().get(scene_hash))
    subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
         "-i", str(src), "-vf", "scale=480:270:flags=neighbor",
         str(tmp / "f%04d.png")], check=True)

    deltas: list[int] = []
    prev = None
    for f in sorted(tmp.glob("f*.png")):
        im = Image.open(f).convert("L")
        if prev is not None:
            diff = ImageChops.difference(im, prev)
            deltas.append(0 if diff.getbbox() is None
                          else sum(1 for p in list(diff.getdata()) if p > 3))
        prev = im
    return deltas


def _longest_run(deltas: list[int]) -> int:
    best = cur = 0
    for n in deltas:
        cur = cur + 1 if n > 0 else 0
        best = max(best, cur)
    return best


def measure(tmp_path, name, template, slots, cues, frames, state="neutral"):
    r = render.render_scene(name, template, slots, cues, frames,
                            resolution_state=state)
    work = tmp_path / name
    work.mkdir()
    try:
        deltas = _frame_deltas(r.hash, work)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return deltas


def ms(frames_count: int) -> float:
    return frames_count / FPS * 1000


# --------------------------------------------------------------- the verbs

def test_reveal_is_spread_across_the_spec_band(tmp_path):
    """§10.1 REVEAL: 300–500 ms. An element that simply enters must not appear
    in one frame."""
    deltas = measure(tmp_path, "v_reveal", "title_card",
                     {"title": "Reading a Learning Curve",
                      "subtitle": "When a model stops learning."}, [], 60)
    run = _longest_run(deltas)
    assert run >= 6, (
        f"REVEAL produced {run} changing frame(s) ({ms(run):.0f}ms); §10.1 "
        f"specifies 300–500ms. One frame means the element is being switched "
        f"on, not revealed.")


def test_build_is_spread_across_the_spec_band(tmp_path):
    """§10.2 BUILD: 400–700 ms, and "previous elements remain stable"."""
    deltas = measure(tmp_path, "v_build", "table_build",
                     {"columns": ["Option", "Cost"],
                      "rows": [{"cells": ["SERIALIZABLE", "retry"]},
                               {"cells": ["Table lock", "stalls"]},
                               {"cells": ["Constraint", "no help"]}]}, [], 120)
    run = _longest_run(deltas)
    assert run >= 8, (
        f"BUILD produced {run} changing frame(s) ({ms(run):.0f}ms); §10.2 "
        f"specifies 400–700ms")


def test_focus_is_spread_and_does_not_strobe(tmp_path):
    """§10.3 FOCUS: 250–450 ms, "avoid pulsing continuously".

    The old behaviour thresholded the focus amount at `> 0.01`, collapsing the
    rise into one frame: measured on the finished video, every blue event was a
    flat 1.4–1.5 s block with no rise and no decay."""
    deltas = measure(tmp_path, "v_focus", "table_build",
                     {"columns": ["Option", "Cost"],
                      "rows": [{"cells": ["SERIALIZABLE", "retry"]},
                               {"cells": ["Table lock", "stalls"]}]},
                     [{"kind": "highlight", "target": "rows[1]",
                       "atSeconds": 1.5, "params": {}}], 90)
    run = _longest_run(deltas)
    assert run >= 5, (
        f"FOCUS produced {run} changing frame(s) ({ms(run):.0f}ms); §10.3 "
        f"specifies 250–450ms. A single-frame colour switch is a flash.")


def test_resolve_is_spread_across_the_spec_band(tmp_path):
    """§10.4 RESOLVE: 400–700 ms — "transition from neutral/signal to answer
    state".

    Driven by the scene's `resolution_state`, which the visual planner sets
    (ISSUE-21). It used to be driven by `highlight_row`, which was the renderer
    inferring pedagogy from layout structure."""
    deltas = measure(tmp_path, "v_resolve", "table_build",
                     {"columns": ["Option", "Cost"],
                      "rows": [{"cells": ["SERIALIZABLE", "retry"]},
                               {"cells": ["Table lock", "stalls"]}]}, [], 90,
                     state="resolved")
    tail = deltas[int(len(deltas) * 0.85):]
    assert _longest_run(tail) >= 4, (
        "RESOLVE produced no spread change at the end of the scene; §10.4 "
        "specifies 400–700ms")


# ------------------------------------------------- the property that failed

def test_a_scene_is_not_mostly_static(tmp_path):
    """The measurement that caught it: 97.3% of the finished video's frames
    were identical to the frame before. A build template with three rows and a
    cue must change on a meaningful share of its frames."""
    deltas = measure(tmp_path, "v_static", "table_build",
                     {"columns": ["Option", "Cost"],
                      "rows": [{"cells": ["SERIALIZABLE", "retry"]},
                               {"cells": ["Table lock", "stalls"]},
                               {"cells": ["Constraint", "no help"]}]},
                     [{"kind": "highlight", "target": "rows[1]",
                       "atSeconds": 2.0, "params": {}}], 120)
    changed = sum(1 for d in deltas if d > 0)
    share = changed / len(deltas)
    assert share > 0.15, (
        f"only {share:.1%} of frames changed. A motion system that produces no "
        f"intermediate frames is not a motion system.")


def test_no_visible_change_happens_in_a_single_frame(tmp_path):
    """The general form of the defect, as a gate rather than a spot check.

    `test_a_scene_is_not_mostly_static` asks whether ANY motion exists, and a
    scene can pass it while still popping: measured on the finished video, the
    `cued` boolean in `concept_illustration` flipped a card's border, surface,
    marker chip and label colour together in ONE frame — 5% of the frame at
    once — inside a scene whose REVEAL was perfectly smooth. A max-run check
    cannot see that.

    Within a single scene there are no cuts to except: §10.5's TRANSITION
    operates between scenes and lives in `assembly`. So every visible change
    inside a scene is one of §10's verbs, and the shortest band is FOCUS at
    250 ms — 7.5 frames. An event above the noise floor that lasts one or two
    frames is therefore a switch, not a verb.
    """
    # EVERY selectable template, not the two whose defects were already known.
    # Checking them one at a time is whack-a-mole: `concept_illustration` and
    # `state_timeline` were fixed, and a per-template re-measure then found the
    # same class of defect again in `table_build` — a discrete fontWeight switch
    # reflowing a whole row in one frame.
    #
    # The cue fires at 5.5 s, AFTER the last BUILD has settled (§10.2's band
    # ends at frame 151 of 180). That separation is the whole fixture: with the
    # cue at 2 s the pop merges into the ongoing build run, no zero-delta frame
    # separates them, and this test passes on known-broken code. Measured on the
    # first defect: three clean 15-frame builds, then 6510 px in ONE frame.
    cases = [
        ("p_concept", "concept_illustration",
         {"caption": "What Repeatable Read guarantees",
          "steps": ["SNAPSHOT AT FIRST READ", "XMIN / XMAX PER ROW",
                    "RULE SPANNING BOTH ROWS"]},
         [{"kind": "highlight", "target": "steps[1]", "atSeconds": 5.5,
           "params": {}}]),
        ("p_timeline", "state_timeline",
         {"tracks": ["Doctor A", "Doctor B"],
          "invariant": "Someone must always stay on call",
          "steps": [{"label": "reads count = 2", "track": "Doctor A"},
                    {"label": "goes off-call", "track": "Doctor B"},
                    {"label": "commits", "track": "Doctor A"}]},
         [{"kind": "highlight", "target": "steps[2]", "atSeconds": 5.5,
           "params": {}}]),
        ("p_table", "table_build",
         {"columns": ["Remedy", "Why it works", "Cost"],
          "rows": [{"cells": ["SERIALIZABLE", "aborts one transaction",
                              "must retry"]},
                   {"cells": ["SELECT FOR UPDATE", "locks the read rows",
                              "only the locked rows"]},
                   {"cells": ["Table lock", "blocks all writers",
                              "stalls everything"]}]},
         [{"kind": "highlight", "target": "rows[1]", "atSeconds": 5.5,
           "params": {}}]),
        ("p_cold", "cold_open",
         {"headline": "How did nobody stay on call?",
          "module_label": "WRITE SKEW",
          "premise_line": "Both transactions commit without a single error."},
         [{"kind": "highlight", "target": "headline", "atSeconds": 5.5,
           "params": {}}]),
        ("p_title", "title_card",
         {"title": "Spot write skew Postgres lets commit",
          "subtitle": "A pair of transactions, no serialization error"},
         [{"kind": "highlight", "target": "subtitle", "atSeconds": 5.5,
           "params": {}}]),
        ("p_phrase", "key_phrase",
         {"phrase": "Reports run often. Write skew is rare but costly.",
          "emphasis": "rare but costly"},
         [{"kind": "scale_pulse", "target": "emphasis", "atSeconds": 5.5,
           "params": {}}]),
    ]
    # Sampled pixels below which a run is dither rather than an element. The
    # finished H.264 MP4 has a real noise floor (runs of 1–20 px, periodic with
    # the GOP); these are near-lossless ProRes intermediates and a probe found
    # NO sub-threshold runs at all, so the floor sits low enough to catch a
    # 32×32 marker chip (~70 px at this sample scale) rather than only a card.
    NOISE = 50
    MIN_FRAMES = 5     # 167ms — under §10.3's 250ms floor with margin for easing

    bad: list[str] = []
    for name, template, slots, cues in cases:
        deltas = measure(tmp_path, name, template, slots, cues, 180)
        run, peak, start = 0, 0, None
        for i, d in enumerate(deltas + [0]):
            if d > 0:
                if start is None:
                    start = i
                run += 1
                peak = max(peak, d)
                continue
            if run and peak >= NOISE and run < MIN_FRAMES:
                bad.append(
                    f"{template}: {peak} px changed over {run} frame(s) "
                    f"({ms(run):.0f}ms) starting at frame {start}")
            run, peak, start = 0, 0, None
    assert not bad, (
        "a visible change completed in under §10.3's shortest band — that is a "
        "switch, not a motion verb:\n  " + "\n  ".join(bad))


def _role_pixels(scene_hash: str, frame_no: int, hex_colour: str) -> int:
    """Pixels within 40 RGB units of a role token, on one full-resolution frame."""
    import numpy as np
    import imageio_ffmpeg
    import tempfile

    tmp = pathlib.Path(tempfile.mkdtemp())
    try:
        src = tmp / "s.mov"
        src.write_bytes(render.store().get(scene_hash))
        out = subprocess.run(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
             "-i", str(src), "-vf", f"select=eq(n\\,{frame_no})", "-frames:v", "1",
             "-pix_fmt", "rgb24", "-f", "rawvideo", "-"], capture_output=True)
        a = np.frombuffer(out.stdout, dtype=np.uint8).reshape(-1, 3).astype(np.float32)
        t = np.array([int(hex_colour[i:i + 2], 16) for i in (1, 3, 5)],
                     dtype=np.float32)
        return int(np.count_nonzero(((a - t) ** 2).sum(axis=1) <= 40 ** 2))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_a_condition_state_holds_but_an_arrival_state_arrives():
    """The onset of a scene's state follows from what the ROLE MEANS.

    s04 is the case that forced this: a 74.5 s scene whose subject is an
    invariant being violated read `broken` only for its last 7.4 s, because
    every state was driven by §10.4's RESOLVE progress of 0.9.

    `broken` and `caution` are CONDITIONS — they hold for the scene. `resolved`
    is an ARRIVAL, and §10.4's late "transition from neutral/signal to answer
    state" is exactly right for it and only for it.

    Measured on a 180-frame scene: the 12 px state rule is 11016 px, absent at
    5% for every state, present from 25% for the conditions, and present for
    the arrival only after frame 174 (97%) — the RESOLVE band runs 162→179, so
    a sample at 95% is still mid-fade and correctly matches nothing.
    """
    slots = {"columns": ["Remedy", "Cost"],
             "rows": [{"cells": ["SERIALIZABLE", "retry"]}]}
    frames = 180
    rule_px = 11016

    for state, token in (("broken", "#D13845"), ("caution", "#FCA106")):
        h = render.render_scene(f"on_{state}", "table_build", slots, [], frames,
                                resolution_state=state).hash
        early = _role_pixels(h, int(frames * 0.25), token)
        assert early == rule_px, (
            f"{state} is a CONDITION and must hold from early in the scene; "
            f"found {early} px of {token} at 25%")
        assert _role_pixels(h, int(frames * 0.05), token) == 0, (
            f"{state} must land after the opening REVEAL, not before it")

    h = render.render_scene("on_resolved", "table_build", slots, [], frames,
                            resolution_state="resolved").hash
    assert _role_pixels(h, int(frames * 0.25), "#05C170") == 0, (
        "resolved is an ARRIVAL — a scene must not read as answered from its "
        "first quarter, or the reveal asserts the conclusion before the "
        "argument")
    assert _role_pixels(h, int(frames * 0.99), "#05C170") == rule_px, (
        "resolved must actually arrive by the end of the scene")


def test_transition_is_not_implemented_in_the_renderer():
    """§10.5 operates between scenes, and §11.4 already models that as a
    first-class node with its own cache key. There is nothing to measure here,
    and that is the correct outcome rather than a missing test."""
    from explainer import assembly
    src = (render.RENDER_DIR / "src" / "motion.ts").read_text(encoding="utf-8")
    assert "export const transition" not in src
    assert hasattr(assembly, "Transition")


def test_a_neutral_scene_has_no_state_treatment(tmp_path):
    """`neutral` means no state claim, so nothing settles into a state colour.
    A scene that tinted anyway would be asserting something the planner did not
    say."""
    neutral = render.render_scene(
        "st_neutral", "table_build",
        {"columns": ["Option", "Cost"],
         "rows": [{"cells": ["SERIALIZABLE", "retry"]}]}, [], 60,
        resolution_state="neutral")
    resolved = render.render_scene(
        "st_resolved", "table_build",
        {"columns": ["Option", "Cost"],
         "rows": [{"cells": ["SERIALIZABLE", "retry"]}]}, [], 60,
        resolution_state="resolved")
    assert neutral.hash != resolved.hash, (
        "the scene state must reach the pixels, and the closure")


def test_each_state_renders_differently(tmp_path):
    """§3's four roles are only useful if they are visually distinct, and that
    has to hold in the OUTPUT, not just the token file."""
    slots = {"columns": ["Option"], "rows": [{"cells": ["SERIALIZABLE"]}]}
    hashes = {
        st: render.render_scene(f"st_{st}", "table_build", slots, [], 45,
                                resolution_state=st).hash
        for st in ("neutral", "broken", "caution", "resolved")
    }
    assert len(set(hashes.values())) == 4, f"states collapsed: {hashes}"

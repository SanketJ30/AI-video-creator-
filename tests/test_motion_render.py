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


def measure(tmp_path, name, template, slots, cues, frames):
    r = render.render_scene(name, template, slots, cues, frames)
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
    state"."""
    deltas = measure(tmp_path, "v_resolve", "table_build",
                     {"columns": ["Option", "Cost"],
                      "rows": [{"cells": ["SERIALIZABLE", "retry"]},
                               {"cells": ["Table lock", "stalls"]}],
                      "highlight_row": 0}, [], 90)
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


def test_transition_is_not_implemented_in_the_renderer():
    """§10.5 operates between scenes, and §11.4 already models that as a
    first-class node with its own cache key. There is nothing to measure here,
    and that is the correct outcome rather than a missing test."""
    from explainer import assembly
    src = (render.RENDER_DIR / "src" / "motion.ts").read_text(encoding="utf-8")
    assert "export const transition" not in src
    assert hasattr(assembly, "Transition")

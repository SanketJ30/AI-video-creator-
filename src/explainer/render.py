"""Scene render — Remotion, §11.1, §11.3, §11.5, CHALLENGES R7/R8.

One scene in, one lossless video chunk out, content-addressed by its closure.

## The closure, and what is deliberately NOT in it

    template · template version · slots · resolved cues · duration in FRAMES ·
    caption safe area · min font px · renderer version · chromium/ffmpeg version

**Not** the scene ref, the video id, the ordinal, or the scene's absolute start
time. §11.4: *"scene renders are position-independent; the cache key must not
include absolute start time"*. That is what makes §11.2's "scene ordering →
invalidate NOTHING at scene level" true, and it is why reordering a video costs
one concat rather than N renders.

Duration enters as an integer frame count, never as seconds. A float would make
two runs that differ in the last bit of a division render twice.

## §11.5 — the licence

Remotion is free for individuals and teams of three or fewer. `LICENSE_KEY` is
`"free-license"`, which is the evaluation clause. Sequence at production volume
is unambiguously "Remotion for Automators" ($0.01/render, $100/mo floor) and
§11.5 says per-render pricing is structurally misaligned with fine-grained
scene re-rendering — which is exactly what this module does. That is a
commercial decision, flagged in §11.5 and not one this file can make.

## §11.3 — hermeticity, and why byte-identity is checked rather than assumed

§11.3: *"periodically render the same scene twice on different workers and
compare digests. Alarm on mismatch. This catches nondeterminism BEFORE it
corrupts the cache."* `check_determinism` does exactly that and is wired into
the CLI, because a cache that returns different bytes for one key is worse than
no cache — the corruption is silent and, as §11.3 says, takes weeks to find.

Intermediates are PNG-sequence-backed lossless (§11.4: *"render intermediates as
lossless/intra-only"*), never lossy inter-frame chunks that would fight over GOP
boundaries at concat time.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from . import hashing, rtime, templates
from .store import store
from .tts import ffmpeg_exe, ffmpeg_version

STAGE = "render_scene"
RENDER_DIR = Path("render")
COMPOSITION = "scene"

# §11.5: the evaluation clause. Not a workaround — the tier is stated in the
# licence and the commercial decision is flagged there.
LICENSE_KEY = "free-license"

# §11.4: "render intermediates as lossless/intra-only (ProRes or MJPEG/FFV1 +
# PCM), concat with -c copy, then a single final encode."
INTERMEDIATE_CODEC = "prores"
INTERMEDIATE_EXT = "mov"
# Remotion rejects ffv1 (it maps a .mkv name to h264-mkv), and §11.4 names
# ProRes first anyway. 4444 is the intra-only, mathematically lossless-enough
# profile; it is pinned because a profile change changes every byte.
PRORES_PROFILE = "4444"


class RenderError(RuntimeError):
    pass


@dataclass
class SceneRender:
    scene_ref: str
    hash: str
    frames: int
    cached: bool = False
    path: str = ""
    props: dict = field(default_factory=dict)


@lru_cache(maxsize=1)
def renderer_version() -> str:
    """§11.3: the renderer version is part of the cache key."""
    pkg = json.loads((RENDER_DIR / "package.json").read_text(encoding="utf-8"))
    return f"remotion@{pkg['dependencies']['remotion']}"


@lru_cache(maxsize=1)
def render_source_version() -> str:
    """Content hash of the renderer's own source.

    §11.3 puts "Chromium / FFmpeg / codec versions" in the cache key because a
    libx264 bump changes bytes. The React that draws the frame is the same class
    of input and was missing: `renderer_version()` is the Remotion PACKAGE
    version, which does not move when Scene.tsx does.

    MEASURED: rewriting `table_build` from a flat list to a real grid produced
    different bytes under an identical closure hash, and `LocalStore.put` raised
    StoreError — invariant 2 doing its job. Without this, every scene rendered
    before a renderer change would be served stale from cache forever, and the
    only symptom would be a video that quietly did not match its own templates.
    """
    files = sorted(list((RENDER_DIR / "src").rglob("*.tsx"))
                   + list((RENDER_DIR / "src").rglob("*.ts"))
                   + [RENDER_DIR / "remotion.config.ts"])
    h = hashlib.sha256()
    for f in files:
        if f.is_file():
            h.update(f.name.encode())
            h.update(f.read_bytes())
    return h.hexdigest()[:16]


@lru_cache(maxsize=1)
def _npx() -> str:
    for name in ("npx.cmd", "npx"):
        found = shutil.which(name)
        if found:
            return found
    raise RenderError("npx not found; Remotion needs Node installed")


def scene_props(template_name: str, slots: dict, cues: list[dict],
                frames: int = 0, resolution_state: str = "neutral") -> dict:
    """The renderer-agnostic spec, translated at the boundary and nowhere else."""
    t = templates.get(template_name)
    return {
        "durationInFrames": int(frames),
        "template": t.name,
        "slots": slots or {},
        "cues": [{"kind": c.get("kind", ""), "target": c.get("target", ""),
                  "atSeconds": float(c.get("atSeconds", 0.0)),
                  "params": c.get("params") or {}}
                 for c in (cues or [])],
        "captionSafeBottom": t.safe_area.bottom,
        "minFontPx": t.min_font_px,
        # §3's scene-level semantic role, decided by the visual planner. In the
        # closure, so a scene whose state changes re-renders.
        "resolutionState": resolution_state or "neutral",
    }


def closure(props: dict, frames: int) -> str:
    """Invariant 1 and §11.4: inputs only, and position is not an input."""
    t = templates.get(props["template"])
    return hashing.closure_hash(
        kind=STAGE,
        upstream={},
        prompt_version=None,
        model_version=None,
        code_version=None,
        config={"renderer": renderer_version(),
                # The renderer's SOURCE, not just its package version. See
                # render_source_version().
                "renderer_source": render_source_version(),
                "ffmpeg": ffmpeg_version(),
                "codec": INTERMEDIATE_CODEC,
                "prores_profile": PRORES_PROFILE,
                "fps": rtime.FPS,
                "width": 1920, "height": 1080,
                "template_version": t.version},
        # `frames` is an integer, never seconds: a float would make two runs
        # that differ in the last bit of a division render twice.
        extra={"props": props, "frames": int(frames)})


def render_scene(scene_ref: str, template_name: str, slots: dict,
                 cues: list[dict], frames: int, *,
                 resolution_state: str = "neutral",
                 force: bool = False) -> SceneRender:
    """Render one scene to a lossless intermediate. Cache hit skips Remotion."""
    props = scene_props(template_name, slots, cues, frames, resolution_state)
    h = closure(props, frames)
    st = store()

    if st.exists(h) and not force:
        return SceneRender(scene_ref=scene_ref, hash=h, frames=frames,
                           cached=True, props=props)

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        props_file = tmpdir / "props.json"
        props_file.write_text(json.dumps(props, ensure_ascii=False),
                              encoding="utf-8")
        out = tmpdir / f"scene.{INTERMEDIATE_EXT}"

        cmd = [_npx(), "remotion", "render", "src/index.ts", COMPOSITION,
               str(out),
               "--props", str(props_file),
               "--codec", INTERMEDIATE_CODEC,
               "--prores-profile", PRORES_PROFILE,
               "--image-format", "png",
               "--concurrency", "1",
               "--log", "error",
               "--license-key", LICENSE_KEY]
        p = subprocess.run(cmd, cwd=RENDER_DIR, capture_output=True, text=True)
        if p.returncode != 0 or not out.exists():
            raise RenderError(
                f"{scene_ref}: remotion render failed (exit {p.returncode})\n"
                f"{(p.stderr or p.stdout)[-2000:]}")
        data = out.read_bytes()

    st.put(h, data, mime=f"video/{INTERMEDIATE_EXT}")
    return SceneRender(scene_ref=scene_ref, hash=h, frames=frames,
                       cached=False, props=props)


def check_determinism(scene_ref: str, template_name: str, slots: dict,
                      cues: list[dict], frames: int) -> tuple[bool, str, str]:
    """§11.3's verification: render twice, compare digests.

    Returns (identical, digest_a, digest_b). The caller decides what to do; this
    function deliberately does not raise, because the interesting case is
    reporting the mismatch with both digests rather than dying.
    """
    props = scene_props(template_name, slots, cues, frames)
    h = closure(props, frames)
    st = store()

    first = render_scene(scene_ref, template_name, slots, cues, frames,
                         force=True)
    a = hashing.content_hash(st.get(first.hash))

    with tempfile.TemporaryDirectory() as tmp:
        # Render again to a scratch location so the store is not overwritten
        # while it is being compared against.
        props_file = Path(tmp) / "props.json"
        props_file.write_text(json.dumps(props, ensure_ascii=False),
                              encoding="utf-8")
        out = Path(tmp) / f"scene.{INTERMEDIATE_EXT}"
        cmd = [_npx(), "remotion", "render", "src/index.ts", COMPOSITION,
               str(out), "--props", str(props_file),
               "--codec", INTERMEDIATE_CODEC, "--prores-profile", PRORES_PROFILE,
               "--image-format", "png",
               "--concurrency", "1", "--log", "error",
               "--license-key", LICENSE_KEY]
        p = subprocess.run(cmd, cwd=RENDER_DIR, capture_output=True, text=True)
        if p.returncode != 0 or not out.exists():
            raise RenderError(
                f"{scene_ref}: second render failed: "
                f"{(p.stderr or p.stdout)[-1500:]}")
        b = hashing.content_hash(out.read_bytes())

    return a == b, a, b


def frame_digest(hash_: str, frame: int = 0) -> str:
    """Perceptual escape hatch from §11.3's last bullet.

    *"Floating-point layout drift across CPU architectures → key on
    architecture, or accept perceptual-hash equality rather than bit
    equality."* When container bytes differ but pixels do not, comparing a
    decoded frame says which of the two happened.
    """
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / f"in.{INTERMEDIATE_EXT}"
        src.write_bytes(store().get(hash_))
        png = Path(tmp) / "f.png"
        cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
               "-i", str(src), "-vf", f"select=eq(n\\,{frame})",
               "-vsync", "0", "-frames:v", "1", str(png)]
        p = subprocess.run(cmd, capture_output=True)
        if p.returncode != 0 or not png.exists():
            raise RenderError(
                f"could not extract frame {frame}: "
                f"{p.stderr.decode(errors='replace')[:400]}")
        return hashing.content_hash(png.read_bytes())


# ------------------------------------------------------- ink coverage (§9.3)
#
# How much of the frame actually has content on it. Added because a scene can
# pass every structural check and still be blank: v2 rendered three `cold_open`
# scenes at 0.00% ink — 33s of a 218s video showing nothing — and no gate
# noticed, because the frames were valid, the durations were right and the
# renders were byte-identical.
#
# This is the visual twin of `assembly._assert_audible`. Both exist because the
# pipeline verified reproducibility and structure while measuring nothing about
# whether there was any signal in the output.

# AUTHORED AND UNREVIEWED. v0.2 gives no ink-coverage number; §9.3 caps how much
# may be on screen and says nothing about a floor. Measured on v2:
#     cold_open  0.00%   (blank)
#     s04 state_timeline  0.53% -> 2.14% across the scene
#     s05 table_build     0.26% -> 4.24%
# so 0.5% separates "blank" from "sparse but real". It is a floor for
# CATCHING BLANKS, not a design target — a legible 1080p frame should be far
# above it, and the fact that this corpus tops out at 4% is itself reportable.
AUTHORED_MIN_INK_COVERAGE = 0.005

# tokens.color.surface. Kept here rather than imported across the language
# boundary; the hex-literal test allows this one because it is a measurement
# parameter, not a style.
# tokens.color.surface (#FFFFFF) — §4's default frame.
BACKGROUND_RGB = (255, 255, 255)


def ink_coverage(hash_: str, frame: int = 0, tolerance: int = 12,
                 step: int = 2) -> float:
    """Fraction of sampled pixels in one rendered frame that are not background.

    `step` subsamples the frame — at 1920x1080 every pixel is 2M reads per frame
    and the number is a coverage estimate, not a checksum. Deterministic: the
    same frame always yields the same value.
    """
    try:
        from PIL import Image
    except ImportError as e:  # pragma: no cover - environment problem
        raise RenderError("Pillow is needed for ink coverage: pip install pillow") from e

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / f"in.{INTERMEDIATE_EXT}"
        src.write_bytes(store().get(hash_))
        png = Path(tmp) / "f.png"
        p = subprocess.run(
            [ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
             "-i", str(src), "-vf", r"select=eq(n\," + str(frame) + ")",
             "-vsync", "0", "-frames:v", "1", str(png)],
            capture_output=True)
        if p.returncode != 0 or not png.exists():
            raise RenderError(
                f"could not extract frame {frame}: "
                f"{p.stderr.decode(errors='replace')[:300]}")
        im = Image.open(png).convert("RGB")

    px = im.load()
    w, h = im.size
    inked = total = 0
    for y in range(0, h, step):
        for x in range(0, w, step):
            r, g, b = px[x, y]
            total += 1
            if (abs(r - BACKGROUND_RGB[0]) > tolerance
                    or abs(g - BACKGROUND_RGB[1]) > tolerance
                    or abs(b - BACKGROUND_RGB[2]) > tolerance):
                inked += 1
    return inked / total if total else 0.0


def coverage_profile(hash_: str, frames: int, samples: int = 4) -> list[float]:
    """Ink coverage sampled across a scene.

    Sampled rather than measured at frame 0 only, because a build template is
    legitimately near-empty at its first frame — judging it there would flag
    every animated scene in the corpus.
    """
    if frames <= 0:
        return []
    picks = sorted({min(frames - 1, int(frames * f))
                    for f in [(i + 1) / (samples + 1) for i in range(samples)]})
    return [ink_coverage(hash_, frame=f) for f in picks]

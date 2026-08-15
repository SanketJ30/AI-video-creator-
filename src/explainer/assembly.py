"""Mux, transitions, concat and captions — §11.4, §16.1, R7.

§11.4 is the hardest correctness section in the spec and this module implements
it literally.

## Sample-accurate concatenation

*"Render intermediates as lossless/intra-only (ProRes or MJPEG/FFV1 + PCM),
concat with `-c copy`, then a single final encode. Never concat lossy
inter-frame chunks — GOP-boundary artifacts and timestamp fights."*

So: each scene is muxed to ProRes + PCM at its resolved frame count, the chunks
are joined with the concat **demuxer** (`-c copy`), and exactly one encode runs
at the end. §11.4 also says *"use the concat demuxer with a manifest, not the
concat filter (which re-encodes)"*, and `-fflags +genpts` resets PTS at the
join, which is the other half of that sentence.

Audio is padded with silence to `pad_audio_to_frame` — never trimmed. At 30 fps
/ 48 kHz a frame is exactly 1600 samples, so a scene's audio and video end on
the same sample and drift cannot accumulate.

## Transitions are first-class nodes with handle frames

§11.4: *"A crossfade between scenes 3 and 4 is a function of both, so it isn't
cacheable under either key. Model transitions as first-class DAG nodes with
handle frames."*

    Transition(i, i+1) = f(tail(scene_i, T), head(scene_{i+1}, T), spec)
    key = H(sceneKey_i, sceneKey_{i+1}, spec, T)

`Transition.closure` is that formula. Editing scene 5 invalidates scene 5,
transition(4,5) and transition(5,6) — three renders, not forty.

**Hard cuts are the default**, per §11.4: pedagogically supported (a fancy
transition is extraneous processing under the coherence principle) and
architecturally cheaper — a cut needs no handle frames and no third render, so
`HARD_CUT` costs nothing and invalidates nothing.

## The stitch manifest

§11.4: *"The stitch manifest is itself content-addressed: H(ordered sceneKeys +
transitionKeys + audioStemKeys + encodeParams). 'Did anything change?' is one
hash comparison, and two courses sharing an intro dedupe for free."*

## Captions (§16.1)

Soft captions, never burn-in: *"Burn-in makes captions part of the render (so a
typo costs a full re-render), breaks per-language reuse, and removes user
control."* WebVTT is primary, SRT is the LMS fallback, and both are written from
**span** timings, which `align.py` measures exactly. Word timings are estimated
and therefore do not drive captions.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import hashing, rtime
from .store import store
from .tts import ffmpeg_exe, ffmpeg_version, read_pcm

HARD_CUT = "cut"
DISSOLVE = "dissolve"

# §11.4's T. Only a dissolve consumes handles; a cut needs none, which is part
# of why §11.4 prefers cuts.
DEFAULT_HANDLE_FRAMES = 15

FINAL_VIDEO_CODEC = "libx264"
FINAL_CRF = "18"
FINAL_PRESET = "slow"
FINAL_AUDIO_CODEC = "aac"
FINAL_AUDIO_BITRATE = "192k"


class AssemblyError(RuntimeError):
    pass


def _assert_audible(path: Path) -> None:
    """A muxed scene whose audio is digital silence is a broken scene.

    This exists because it happened: the first full render produced a correct
    1080p file at -91 dB throughout, and nothing in the pipeline noticed. Every
    duration, hash, caption and frame count was right. The check is cheap and it
    is the difference between shipping a video and shipping a silent one.
    """
    p = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path),
                        "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True)
    for line in (p.stderr or "").splitlines():
        if "max_volume:" in line:
            db = float(line.split("max_volume:")[1].replace("dB", "").strip())
            if db < -60.0:
                raise AssemblyError(
                    f"{path.name}: muxed audio peaks at {db} dB — that is "
                    f"silence. The narration did not reach the file.")
            return
    raise AssemblyError(f"could not measure audio level of {path}")


def _run(cmd: list[str], what: str) -> None:
    p = subprocess.run(cmd, capture_output=True)
    if p.returncode != 0:
        raise AssemblyError(
            f"{what} failed: {p.stderr.decode(errors='replace')[-1500:]}")


# ------------------------------------------------------------- transitions

@dataclass(frozen=True)
class Transition:
    """§11.4's first-class node between two scenes."""

    kind: str = HARD_CUT
    handle_frames: int = 0

    def closure(self, scene_key_a: str, scene_key_b: str) -> str:
        """key = H(sceneKey_i, sceneKey_{i+1}, spec, T) — §11.4, literally."""
        return hashing.closure_hash(
            kind="transition", upstream={"a": scene_key_a, "b": scene_key_b},
            prompt_version=None, model_version=None, code_version=None,
            config={"ffmpeg": ffmpeg_version()},
            extra={"kind": self.kind, "handle_frames": self.handle_frames})

    @property
    def consumes_handles(self) -> bool:
        return self.kind != HARD_CUT


def default_transitions(n_scenes: int) -> list[Transition]:
    """§11.4: 'Prefer hard cuts by default.' Dissolves are offered only at
    module boundaries, which this pipeline does not model yet."""
    return [Transition(HARD_CUT, 0) for _ in range(max(0, n_scenes - 1))]


# -------------------------------------------------------------------- mux

def mux_scene(video_hash: str, audio_hash: str, frames: int,
              audio_samples_target: int, pad_plan=None,
              span_samples: list[int] | None = None) -> str:
    """One scene's picture + narration, padded to an exact frame count.

    Returns the content hash of the muxed chunk. Audio is padded with silence
    and never trimmed: trimming would cut the end off a sentence, and §11.4's
    whole argument for integer frame counts is that the pad is exact.
    """
    h = hashing.closure_hash(
        kind="mux_scene", upstream={"video": video_hash, "audio": audio_hash},
        prompt_version=None, model_version=None, code_version=None,
        config={"ffmpeg": ffmpeg_version(), "fps": rtime.FPS,
                "sample_rate": rtime.SAMPLE_RATE,
                # In the closure because it changes which audio ends up in the
                # file. Without it, muxes made before the explicit -map was
                # added would be served from cache and stay silent.
                "stream_map": "0:v:0+1:a:0"},
        extra={"frames": int(frames), "samples": int(audio_samples_target),
               # In the closure: the same audio padded differently is a
               # different scene, and serving one for the other would put the
               # silence back where ISSUE-14 found it.
               "pad_plan": pad_plan.to_json() if pad_plan else None})
    st = store()
    if st.exists(h):
        return h

    pcm = read_pcm(audio_hash)
    have = len(pcm) // 2
    if have < audio_samples_target:
        pcm = pcm + b"\x00" * ((audio_samples_target - have) * 2)
    elif have > audio_samples_target:
        raise AssemblyError(
            f"audio is {have} samples but the resolved duration is "
            f"{audio_samples_target}. The resolver pads up and never trims; "
            f"this means the timeline and the audio disagree.")

    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        vin, ain, out = d / "v.mov", d / "a.raw", d / "out.mov"
        vin.write_bytes(st.get(video_hash))
        ain.write_bytes(pcm)
        _run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
              "-i", str(vin),
              "-f", "s16le", "-ar", str(rtime.SAMPLE_RATE), "-ac", "1",
              "-i", str(ain),
              # EXPLICIT stream mapping, and it is load-bearing. Remotion's
              # ProRes output already carries a SILENT stereo PCM track, and
              # ffmpeg's default audio selection prefers more channels — so it
              # picked Remotion's silence over this mono narration and produced
              # a video at -91 dB. Measured, not theorised.
              "-map", "0:v:0", "-map", "1:a:0",
              "-c:v", "copy",
              # PCM keeps the intermediate lossless (§11.4).
              "-c:a", "pcm_s16le",
              "-shortest", str(out)], "mux")
        data = out.read_bytes()
        _assert_audible(out)
    st.put(h, data, mime="video/mov")
    return h


# ----------------------------------------------------------------- concat

@dataclass
class StitchManifest:
    """§11.4: content-addressed, so 'did anything change?' is one comparison."""

    scene_keys: list[str]
    transition_keys: list[str] = field(default_factory=list)
    audio_stem_keys: list[str] = field(default_factory=list)
    encode_params: dict = field(default_factory=dict)

    def hash(self) -> str:
        return hashing.sha256_hex(hashing.canonical_json({
            "scenes": self.scene_keys,
            "transitions": self.transition_keys,
            "audio_stems": self.audio_stem_keys,
            "encode": self.encode_params}))

    def to_json(self) -> dict:
        return {"hash": self.hash(), "scenes": self.scene_keys,
                "transitions": self.transition_keys,
                "audio_stems": self.audio_stem_keys,
                "encode": self.encode_params}


def encode_params() -> dict:
    return {"video": FINAL_VIDEO_CODEC, "crf": FINAL_CRF,
            "preset": FINAL_PRESET, "audio": FINAL_AUDIO_CODEC,
            "audio_bitrate": FINAL_AUDIO_BITRATE,
            "fps": rtime.FPS, "sample_rate": rtime.SAMPLE_RATE,
            "ffmpeg": ffmpeg_version()}


def concat_and_encode(chunk_hashes: list[str], out_path: Path,
                      transitions: list[Transition] | None = None) -> Path:
    """§11.4: concat demuxer with `-c copy`, then ONE final encode.

    The concat *filter* re-encodes and is explicitly rejected by §11.4.
    """
    if not chunk_hashes:
        raise AssemblyError("nothing to concat")
    transitions = transitions or default_transitions(len(chunk_hashes))
    if any(t.consumes_handles for t in transitions):
        raise AssemblyError(
            "dissolve transitions need handle frames rendered beyond nominal "
            "duration; only hard cuts are implemented. §11.4 prefers cuts by "
            "default and offers dissolves at module boundaries, which this "
            "pipeline does not model yet.")

    st = store()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        listing = d / "concat.txt"
        lines = []
        for i, h in enumerate(chunk_hashes):
            p = d / f"c{i:03d}.mov"
            p.write_bytes(st.get(h))
            lines.append(f"file '{p.as_posix()}'")
        listing.write_text("\n".join(lines) + "\n", encoding="utf-8")

        joined = d / "joined.mov"
        _run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
              # §11.4: "Explicitly reset PTS at concat; use the concat demuxer
              # with a manifest, not the concat filter (which re-encodes)."
              "-fflags", "+genpts",
              "-f", "concat", "-safe", "0", "-i", str(listing),
              "-c", "copy", str(joined)], "concat")

        _run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
              "-i", str(joined),
              "-c:v", FINAL_VIDEO_CODEC, "-crf", FINAL_CRF,
              "-preset", FINAL_PRESET, "-pix_fmt", "yuv420p",
              "-r", str(rtime.FPS),
              "-c:a", FINAL_AUDIO_CODEC, "-b:a", FINAL_AUDIO_BITRATE,
              "-ar", str(rtime.SAMPLE_RATE),
              "-movflags", "+faststart",
              str(out_path)], "final encode")
    return out_path


def probe_duration(path: Path) -> float:
    """Measured runtime of a finished file. ffprobe is not shipped with
    imageio-ffmpeg, so this reads ffmpeg's own report of the input."""
    p = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path)],
                       capture_output=True, text=True)
    for line in (p.stderr or "").splitlines():
        if "Duration:" in line:
            clock = line.split("Duration:")[1].split(",")[0].strip()
            hh, mm, ss = clock.split(":")
            return int(hh) * 3600 + int(mm) * 60 + float(ss)
    raise AssemblyError(f"could not read duration of {path}")


# --------------------------------------------------------------- captions

def _vtt_clock(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _srt_clock(seconds: float) -> str:
    return _vtt_clock(seconds).replace(".", ",")


def caption_cues(timeline) -> list[tuple[float, float, str]]:
    """Absolute (start, end, text) per span across the whole video.

    Span level, not word level: §16.1 drives kinetic typography from the word
    sidecar, but span boundaries are the ones `align.py` MEASURES. Captions are
    a WCAG 1.2.2 obligation and must not be built on estimates.
    """
    out: list[tuple[float, float, str]] = []
    starts = timeline.starts()
    for scene in timeline.scenes:
        offset = starts[scene.scene_ref].seconds
        for span in scene.spans:
            text = (span.get("text") or "").strip()
            if not text:
                continue
            out.append((offset + span["start"] / rtime.SAMPLE_RATE,
                        offset + span["end"] / rtime.SAMPLE_RATE, text))
    return out


def to_webvtt(timeline) -> str:
    """§16.1: WebVTT is primary — it supports inline timestamp tags."""
    lines = ["WEBVTT", ""]
    for i, (start, end, text) in enumerate(caption_cues(timeline), start=1):
        lines += [str(i), f"{_vtt_clock(start)} --> {_vtt_clock(end)}", text, ""]
    return "\n".join(lines)


def to_srt(timeline) -> str:
    """§16.1: SRT is the universal LMS fallback."""
    lines = []
    for i, (start, end, text) in enumerate(caption_cues(timeline), start=1):
        lines += [str(i), f"{_srt_clock(start)} --> {_srt_clock(end)}", text, ""]
    return "\n".join(lines)


def to_word_sidecar(timeline) -> str:
    """§16.1's 'JSON word-timing sidecar (your own format)'.

    Every word carries the method that produced it, so a consumer can tell a
    measured boundary from an estimated one. Do not overload WebVTT for this —
    §16.1 says so explicitly.
    """
    starts = timeline.starts()
    doc = {"fps": rtime.FPS, "sampleRate": rtime.SAMPLE_RATE, "scenes": []}
    for scene in timeline.scenes:
        offset = starts[scene.scene_ref].samples
        doc["scenes"].append({
            "ref": scene.scene_ref,
            "startSamples": offset,
            "spans": [{**s,
                       "absoluteStart": offset + s["start"],
                       "absoluteEnd": offset + s["end"]}
                      for s in scene.spans]})
    return json.dumps(doc, indent=2, ensure_ascii=False)

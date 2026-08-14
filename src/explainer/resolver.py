"""The two-phase timing resolver — §11.2, §11.4, §15.3, CHALLENGES R1/R2/R5.

§11.2, quoting Blender's lesson: *"two-phase tag-then-flush — resolve all
durations/timing globally first, then render pixels — never interleave, because
durations cascade."*

That is the whole shape of this module. `resolve()` takes every scene's audio
and returns a `Timeline` in which every duration, every scene offset and every
cue time is already concrete. Nothing renders until that object exists. The
alternative — resolving a scene, rendering it, moving on — means a change to
scene 2's narration silently invalidates the pixels of scenes 3..N, which is the
After Effects failure §11.2 warns about.

## R1 — durations are stored, positions are derived

`SceneTiming.duration` is stored. `SceneTiming.start` is computed by
accumulation in `Timeline`, and is deliberately NOT part of any cache key: §11.4
says *"scene renders are position-independent; the cache key must not include
absolute start time"*. Reordering scenes therefore costs a manifest rewrite and
one concat, not forty re-renders.

Cue times are likewise **local to the scene**. A cue resolved to an absolute
timeline position would make the scene's render depend on where it sits.

## §11.4 — integer frame counts, always

*"Force integer frame counts for every scene duration. Pad TTS audio with
silence to ceil(samples / samplesPerFrame) × samplesPerFrame."* Every duration
this module produces is frame-aligned, and `Timeline` asserts it before
returning. At 30 fps / 48 kHz a frame is exactly 1600 samples, so the alignment
is exact rather than a rounding convention.

## §15.3 — rigid versus elastic

| sensitivity | duration | audio |
|---|---|---|
| `elastic` | derived from the audio (R5), then padded up to the frame | as synthesised |
| `rigid` | the authored target, frame-aligned | fitted into it |

Rigid exists for scenes whose visual has its own tempo — a timeline animation
that lands on a beat. Fitting is silence padding only. §15.3 caps that at ~15%
of scene duration and says **never speed TTS beyond +8%**; this module does not
time-stretch at all, so an overrun is reported rather than papered over. A rigid
scene whose audio does not fit is a `FitProblem`, not a silent trim: trimming
would cut words off the end of a sentence.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import rtime
from .rtime import RationalTime

# §15.3: "silence padding up to ~15% of scene duration to absorb contraction;
# beyond that, re-render at the new duration."
MAX_SILENCE_PAD_SHARE = 0.15


class ResolveError(RuntimeError):
    pass


@dataclass(frozen=True)
class FitProblem:
    """A rigid scene whose audio does not fit its authored duration."""

    scene_ref: str
    audio_seconds: float
    duration_seconds: float
    kind: str            # "overrun" | "excessive_padding"
    detail: str

    def __str__(self) -> str:
        return f"{self.scene_ref}: {self.detail}"


@dataclass
class CueTiming:
    """A cue resolved from its span anchor to a concrete LOCAL time (R3)."""

    kind: str
    target: str
    span_id: str
    at: RationalTime          # local to the scene, never absolute
    offset_ms: int = 0
    params: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return {"kind": self.kind, "target": self.target,
                "spanId": self.span_id,
                "atSamples": self.at.rescale_to(rtime.SAMPLE_RATE).value,
                "atSeconds": round(self.at.seconds, 6),
                "offsetMs": self.offset_ms, "params": self.params}


@dataclass
class SceneTiming:
    scene_ref: str
    duration: RationalTime               # stored (R1), frame-aligned
    audio_hash: str
    audio_samples: int                   # before padding
    padded_samples: int                  # after padding, == duration in samples
    timing_sensitivity: str
    cues: list[CueTiming] = field(default_factory=list)
    spans: list[dict] = field(default_factory=list)
    per_span_fallback: bool = False

    @property
    def frames(self) -> int:
        return self.duration.frames

    @property
    def silence_samples(self) -> int:
        return self.padded_samples - self.audio_samples

    def to_json(self) -> dict:
        return {"scene_ref": self.scene_ref,
                "durationSamples": self.padded_samples,
                "durationFrames": self.frames,
                "durationSeconds": round(self.duration.seconds, 6),
                "audioHash": self.audio_hash,
                "audioSamples": self.audio_samples,
                "silenceSamples": self.silence_samples,
                "timingSensitivity": self.timing_sensitivity,
                "perSpanFallback": self.per_span_fallback,
                "cues": [c.to_json() for c in self.cues],
                "spans": self.spans}


@dataclass
class Timeline:
    """Every duration resolved. Positions derived, never stored (R1)."""

    scenes: list[SceneTiming]
    problems: list[FitProblem] = field(default_factory=list)

    @property
    def total(self) -> RationalTime:
        return rtime.sum_durations([s.duration for s in self.scenes])

    @property
    def total_frames(self) -> int:
        return sum(s.frames for s in self.scenes)

    def starts(self) -> dict[str, RationalTime]:
        """Absolute offsets, DERIVED. Not a cache key input (§11.4)."""
        out: dict[str, RationalTime] = {}
        cursor = RationalTime.zero()
        for s in self.scenes:
            out[s.scene_ref] = cursor
            cursor = cursor + s.duration
        return out

    def to_json(self) -> dict:
        starts = self.starts()
        return {"fps": rtime.FPS, "sampleRate": rtime.SAMPLE_RATE,
                "totalFrames": self.total_frames,
                "totalSeconds": round(self.total.seconds, 6),
                "scenes": [{**s.to_json(),
                            "startFrames": starts[s.scene_ref].frames}
                           for s in self.scenes],
                "problems": [str(p) for p in self.problems]}


# --------------------------------------------------------------- resolution

def resolve_cue(cue: dict, alignment, scene_duration: RationalTime) -> CueTiming:
    """R3: span id + offset -> a concrete local time.

    Clamped into the scene. A cue with a -100 ms offset on the first span would
    otherwise land at a negative time, and a negative cue time is not a signal
    that fires early — it is one that never fires.
    """
    anchor = cue.get("anchor") or {}
    span_id = anchor.get("spanId") or cue.get("span_id") or ""
    offset_ms = int((anchor.get("offset") or {}).get("value",
                                                     cue.get("offset_ms", 0)))
    point = anchor.get("point", cue.get("point", "start"))

    span = alignment.resolve(span_id)
    base_samples = span.start if point == "start" else span.end
    at_samples = base_samples + int(round(offset_ms * rtime.SAMPLE_RATE / 1000))
    at_samples = max(0, min(at_samples,
                            scene_duration.rescale_to(rtime.SAMPLE_RATE).value))
    return CueTiming(kind=cue.get("kind", ""), target=cue.get("target", ""),
                     span_id=span_id,
                     at=RationalTime.from_samples(at_samples, rtime.SAMPLE_RATE),
                     offset_ms=offset_ms, params=cue.get("params") or {})


def resolve_scene(scene_ref: str, speech, timing_sensitivity: str,
                  target_seconds: int | None,
                  cues: list[dict] | None = None) -> tuple[SceneTiming,
                                                           list[FitProblem]]:
    """One scene's duration and cue times. `speech` is a `speech.SceneSpeech`."""
    audio_samples = speech.audio.sample_count
    problems: list[FitProblem] = []

    if timing_sensitivity == "rigid":
        if not target_seconds:
            raise ResolveError(
                f"{scene_ref}: a rigid scene needs an authored duration, but "
                f"target_seconds is {target_seconds!r}. Rigid means the visual "
                f"owns the tempo; without a target there is nothing to be rigid "
                f"about.")
        padded = rtime.pad_audio_to_frame(
            int(round(target_seconds * rtime.SAMPLE_RATE)))
        if audio_samples > padded:
            over = (audio_samples - padded) / rtime.SAMPLE_RATE
            problems.append(FitProblem(
                scene_ref, audio_samples / rtime.SAMPLE_RATE,
                padded / rtime.SAMPLE_RATE, "overrun",
                f"rigid scene holds {padded / rtime.SAMPLE_RATE:.2f}s but its "
                f"narration is {audio_samples / rtime.SAMPLE_RATE:.2f}s "
                f"({over:.2f}s over). §15.3 forbids speeding TTS beyond +8% and "
                f"trimming would cut the end off a sentence, so the scene is "
                f"left long: either shorten the narration or make it elastic."))
            # Do not trim. The overrun is carried and reported.
            padded = rtime.pad_audio_to_frame(audio_samples)
        else:
            share = (padded - audio_samples) / padded if padded else 0.0
            if share > MAX_SILENCE_PAD_SHARE:
                problems.append(FitProblem(
                    scene_ref, audio_samples / rtime.SAMPLE_RATE,
                    padded / rtime.SAMPLE_RATE, "excessive_padding",
                    f"rigid scene pads {share:.0%} of its duration with "
                    f"silence; §15.3 budgets {MAX_SILENCE_PAD_SHARE:.0%}. "
                    f"Beyond that the scene should be re-cut, not stretched."))
    else:
        # Elastic (§15.3 strategy A): duration derived from the audio (R5).
        padded = rtime.pad_audio_to_frame(audio_samples)

    duration = RationalTime.from_samples(padded, rtime.SAMPLE_RATE)
    if not duration.is_frame_aligned():
        raise ResolveError(
            f"{scene_ref}: resolved duration {duration} is not frame-aligned. "
            f"§11.4 requires integer frame counts for sample-accurate concat.")

    resolved_cues = [resolve_cue(c, speech.alignment, duration)
                     for c in (cues or [])]

    return SceneTiming(
        scene_ref=scene_ref, duration=duration,
        audio_hash=speech.audio.hash, audio_samples=audio_samples,
        padded_samples=padded, timing_sensitivity=timing_sensitivity,
        cues=resolved_cues,
        spans=[s.to_json() for s in speech.alignment.spans],
        per_span_fallback=speech.per_span_fallback), problems


def resolve(scenes: list[dict]) -> Timeline:
    """Phase one, whole video. Nothing renders until this returns.

    Each entry: {ref, speech, timing_sensitivity, target_seconds, cues}.
    """
    out: list[SceneTiming] = []
    problems: list[FitProblem] = []
    for s in scenes:
        timing, probs = resolve_scene(
            s["ref"], s["speech"], s.get("timing_sensitivity") or "elastic",
            s.get("target_seconds"), s.get("cues"))
        out.append(timing)
        problems += probs

    timeline = Timeline(scenes=out, problems=problems)
    # §11.4: the whole point of integer frame counts is that the sum is exact.
    rtime.assert_no_drift([s.duration for s in out])
    return timeline

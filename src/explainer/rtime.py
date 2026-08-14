"""RationalTime (PRD v0.2 §5.2 R2).

    "Steal OTIO's RationalTime (integer value + integer rate). Never store
     seconds as a float; never store a frame count without its rate. This
     eliminates an entire class of drift bugs. Use integer fps (30) and 48 kHz —
     30 fps x 48 kHz = exactly 1600 samples/frame. 29.97 gives 1601.6 and
     guarantees accumulating drift across 40 scenes."

Everything here is exact integer/Fraction arithmetic. There is deliberately NO
way to construct a RationalTime from a float, because that is the hole through
which drift enters. `from_seconds` takes a Fraction, an int, or a decimal string.

Why this is week-one work rather than later work: durations are derived from TTS
output, summed across scenes, converted to frames for the renderer and to samples
for the audio muxer. If any single conversion rounds, a 40-scene video ends with
audio and video visibly out of step, and the bug presents as "the video feels
slightly wrong" with no stack trace. See CHALLENGES R1.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import gcd
from typing import Union

# §5.2 R2 and §11.4. These are not defaults to be tuned; they are a compatibility
# contract. 48000 / 30 = 1600 samples per frame, exactly.
FPS = 30
SAMPLE_RATE = 48000
SAMPLES_PER_FRAME = SAMPLE_RATE // FPS

Number = Union[int, Fraction, str]


class TimeError(ValueError):
    pass


@dataclass(frozen=True, order=False)
class RationalTime:
    """An exact instant or duration: `value` ticks at `rate` ticks per second."""

    value: int
    rate: int = FPS

    def __post_init__(self) -> None:
        if not isinstance(self.value, int) or isinstance(self.value, bool):
            raise TimeError(f"value must be an int, got {type(self.value).__name__}. "
                            "Floats are rejected on purpose — see module docstring.")
        if not isinstance(self.rate, int) or self.rate <= 0:
            raise TimeError(f"rate must be a positive int, got {self.rate!r}")

    # ---------------------------------------------------------- constructors

    @classmethod
    def from_frames(cls, frames: int, fps: int = FPS) -> "RationalTime":
        return cls(frames, fps)

    @classmethod
    def from_samples(cls, samples: int, sample_rate: int = SAMPLE_RATE) -> "RationalTime":
        return cls(samples, sample_rate)

    @classmethod
    def from_seconds(cls, seconds: Number, rate: int = FPS) -> "RationalTime":
        """Exact only. Pass an int, a Fraction, or a decimal *string* ("1.5").

        A float is refused rather than silently accepted: float('0.1') is not
        one tenth, and the error compounds once you sum 40 of them.
        """
        if isinstance(seconds, float):
            raise TimeError(
                "from_seconds refuses floats. Use a decimal string "
                'RationalTime.from_seconds("1.5") or a Fraction.')
        frac = Fraction(seconds)
        ticks = frac * rate
        if ticks.denominator != 1:
            raise TimeError(
                f"{seconds} seconds is not representable at rate {rate} "
                f"({ticks} ticks). Round explicitly with ceil_to_frame() so the "
                "rounding is a visible decision, not a silent one.")
        return cls(int(ticks), rate)

    @classmethod
    def zero(cls, rate: int = FPS) -> "RationalTime":
        return cls(0, rate)

    # ------------------------------------------------------------ conversion

    @property
    def seconds(self) -> Fraction:
        """Exact seconds as a Fraction. Never returns a float."""
        return Fraction(self.value, self.rate)

    def rescale_to(self, rate: int) -> "RationalTime":
        """Exact rate change. Raises if it would not be exact."""
        ticks = Fraction(self.value * rate, self.rate)
        if ticks.denominator != 1:
            raise TimeError(
                f"{self} cannot be expressed exactly at rate {rate}. "
                "This is the drift you are trying to avoid — pad to a frame "
                "boundary first (see pad_to_frame).")
        return RationalTime(int(ticks), rate)

    @property
    def frames(self) -> int:
        return self.rescale_to(FPS).value

    @property
    def samples(self) -> int:
        return self.rescale_to(SAMPLE_RATE).value

    def float_seconds(self) -> float:
        """ONLY for display and for handing to FFmpeg/Remotion at the boundary.
        Never feed this back into a calculation."""
        return self.value / self.rate

    # ------------------------------------------------------------ arithmetic

    @staticmethod
    def _common(a: "RationalTime", b: "RationalTime") -> tuple[int, int, int]:
        if a.rate == b.rate:
            return a.value, b.value, a.rate
        rate = a.rate * b.rate // gcd(a.rate, b.rate)   # lcm
        return a.value * (rate // a.rate), b.value * (rate // b.rate), rate

    def __add__(self, other: "RationalTime") -> "RationalTime":
        av, bv, rate = self._common(self, other)
        return RationalTime(av + bv, rate)

    def __sub__(self, other: "RationalTime") -> "RationalTime":
        av, bv, rate = self._common(self, other)
        return RationalTime(av - bv, rate)

    def __mul__(self, k: int) -> "RationalTime":
        if not isinstance(k, int) or isinstance(k, bool):
            raise TimeError("multiply by an int only; scaling by a float reintroduces drift")
        return RationalTime(self.value * k, self.rate)

    def __neg__(self) -> "RationalTime":
        return RationalTime(-self.value, self.rate)

    # ------------------------------------------------------------ comparison

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RationalTime):
            return NotImplemented
        return self.seconds == other.seconds       # 30@30fps == 48000@48kHz

    def __lt__(self, other: "RationalTime") -> bool:
        return self.seconds < other.seconds

    def __le__(self, other: "RationalTime") -> bool:
        return self.seconds <= other.seconds

    def __gt__(self, other: "RationalTime") -> bool:
        return self.seconds > other.seconds

    def __ge__(self, other: "RationalTime") -> bool:
        return self.seconds >= other.seconds

    def __hash__(self) -> int:
        return hash(self.seconds)

    # -------------------------------------------------------------- rounding

    def ceil_to_frame(self, fps: int = FPS) -> "RationalTime":
        """Round up to a whole frame. §11.4: force integer frame counts for
        every scene duration so concatenation stays sample-accurate."""
        ticks = Fraction(self.value * fps, self.rate)
        frames = -((-ticks.numerator) // ticks.denominator)   # ceil for Fractions
        return RationalTime(int(frames), fps)

    def is_frame_aligned(self, fps: int = FPS) -> bool:
        return Fraction(self.value * fps, self.rate).denominator == 1

    # --------------------------------------------------------- serialisation

    def to_json(self) -> dict:
        return {"value": self.value, "rate": self.rate}

    @classmethod
    def from_json(cls, obj: dict) -> "RationalTime":
        return cls(int(obj["value"]), int(obj["rate"]))

    def __repr__(self) -> str:
        return f"RationalTime({self.value}, {self.rate})"

    def __str__(self) -> str:
        total = self.float_seconds()
        return f"{total:.3f}s ({self.value}@{self.rate})"


# ------------------------------------------------------------------- helpers

ZERO = RationalTime(0, FPS)


def pad_audio_to_frame(sample_count: int) -> int:
    """§11.4: pad TTS audio with silence to ceil(samples / samplesPerFrame) x
    samplesPerFrame, so every scene is a whole number of frames AND a whole
    number of audio blocks. This is what makes `-c copy` concatenation exact."""
    blocks = -(-sample_count // SAMPLES_PER_FRAME)
    return blocks * SAMPLES_PER_FRAME


def sum_durations(durations: list[RationalTime]) -> RationalTime:
    """Exact sum. The whole point of this module is that this cannot drift."""
    total = RationalTime(0, FPS)
    for d in durations:
        total = total + d
    return total


def assert_no_drift(durations: list[RationalTime]) -> None:
    """Every scene duration must be frame-aligned before assembly (§11.4)."""
    bad = [i for i, d in enumerate(durations) if not d.is_frame_aligned()]
    if bad:
        raise TimeError(
            f"scenes at index {bad} are not frame-aligned. Call "
            "ceil_to_frame() when the duration is derived from TTS, not at "
            "assembly time — rounding late is how sync drifts.")

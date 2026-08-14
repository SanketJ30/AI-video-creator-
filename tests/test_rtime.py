"""RationalTime tests (PRD R2, §11.4).

The point of these is one number: 30 fps x 48 kHz = exactly 1600 samples/frame.
If any of these fail, A/V sync drifts across a long video and the symptom is
"it feels slightly off" with no traceable cause — CHALLENGES R1.
"""
from fractions import Fraction

import pytest

from explainer.rtime import (FPS, SAMPLE_RATE, SAMPLES_PER_FRAME, RationalTime,
                             TimeError, assert_no_drift, pad_audio_to_frame,
                             sum_durations)


def test_the_contract_number():
    assert SAMPLES_PER_FRAME == 1600
    assert SAMPLE_RATE % FPS == 0, "non-integer samples/frame guarantees drift"


def test_floats_are_refused():
    with pytest.raises(TimeError):
        RationalTime(1.5, FPS)          # type: ignore[arg-type]
    with pytest.raises(TimeError):
        RationalTime.from_seconds(1.5)


def test_decimal_strings_and_fractions_are_exact():
    assert RationalTime.from_seconds("1.5").value == 45
    assert RationalTime.from_seconds(Fraction(1, 2)).value == 15


def test_inexact_seconds_are_refused_not_rounded():
    # 0.01s is not representable at 30fps. Silently rounding here is the bug.
    with pytest.raises(TimeError):
        RationalTime.from_seconds("0.01")


def test_equality_across_rates():
    assert RationalTime(30, 30) == RationalTime(48000, 48000)
    assert RationalTime(1, 30) == RationalTime(1600, 48000)


def test_addition_across_rates_is_exact():
    a = RationalTime(1, 30)        # one frame
    b = RationalTime(1600, 48000)  # one frame, expressed in samples
    assert (a + b).seconds == Fraction(2, 30)


def test_no_drift_over_forty_scenes():
    """The specific claim in §5.2 R2: 30/48k survives 40 scenes; 29.97 does not."""
    durations = [RationalTime(37, FPS)] * 40      # 40 scenes of 37 frames
    total = sum_durations(durations)
    assert total.frames == 1480
    assert total.samples == 1480 * 1600
    assert total.seconds == Fraction(1480, 30)    # exact, no accumulated error


def test_2997_is_the_rate_that_drifts():
    """§5.2 R2's actual claim: 30x48000 divides exactly; 29.97 does not.

    At 29.97 fps a frame is 1601.6 samples, so no whole number of samples is a
    whole number of frames — every scene boundary lands mid-sample and the error
    accumulates across a 40-scene video. This test pins the arithmetic rather
    than trusting the comment.
    """
    assert Fraction(SAMPLE_RATE, FPS).denominator == 1          # 1600, exact
    assert Fraction(SAMPLE_RATE * 1000, 29970).denominator != 1  # 1601.6, not exact


def test_ceil_to_frame():
    t = RationalTime(1601, SAMPLE_RATE)          # just over one frame
    assert t.ceil_to_frame().value == 2
    assert RationalTime(1600, SAMPLE_RATE).ceil_to_frame().value == 1


def test_rescale_refuses_inexact():
    with pytest.raises(TimeError):
        RationalTime(1601, SAMPLE_RATE).frames   # not a whole frame


def test_pad_audio_to_frame():
    assert pad_audio_to_frame(1) == 1600
    assert pad_audio_to_frame(1600) == 1600
    assert pad_audio_to_frame(1601) == 3200
    # every padded length is a whole number of frames AND of audio blocks
    for n in (1, 999, 48000, 70001):
        assert pad_audio_to_frame(n) % SAMPLES_PER_FRAME == 0


def test_assert_no_drift_flags_unaligned_scenes():
    good = [RationalTime(30, FPS), RationalTime(48000, SAMPLE_RATE)]
    assert_no_drift(good)
    with pytest.raises(TimeError, match="index"):
        assert_no_drift([RationalTime(1601, SAMPLE_RATE)])


def test_multiplication_by_float_refused():
    with pytest.raises(TimeError):
        RationalTime(30, FPS) * 1.5   # type: ignore[operator]


def test_ordering():
    assert RationalTime(1, 30) < RationalTime(2, 30)
    assert RationalTime(1600, 48000) <= RationalTime(1, 30)
    assert max(RationalTime(5, 30), RationalTime(2, 30)).value == 5

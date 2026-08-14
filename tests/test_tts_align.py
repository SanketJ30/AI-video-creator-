"""TTS and forced alignment — §16.1, §11.3, §11.4, R3/R4/R5.

The pure functions are tested directly; synthesis is exercised on two short
strings because determinism and the closure are the properties that matter and
neither can be checked without running the thing. No network: piper is local and
the voice is a pinned file under var/voices.
"""
from __future__ import annotations

import pytest

from explainer import align as A
from explainer import rtime, tts
from explainer.spans import Narration

pytestmark = pytest.mark.skipif(
    not (tts.VOICE_DIR / "en_US-lessac-medium.onnx").exists(),
    reason="pinned voice not downloaded; see tts.TTSError guidance")

SHORT = "Two doctors are on call tonight."
TWO = "Two doctors are on call tonight. Both of them go off duty."


# ------------------------------------------------------------------ lexicon

def test_the_lexicon_is_whole_word_and_case_insensitive():
    lex = tts.load_lexicon("en.v1")
    assert "Post gress" in lex.apply("Postgres commits")
    assert "Post gress" in lex.apply("POSTGRES commits")
    assert lex.apply("prefixmin") == "prefixmin"


def test_the_lexicon_prefers_the_longer_entry():
    """Without longest-first, SQL would eat PostgreSQL."""
    lex = tts.load_lexicon("en.v1")
    assert lex.apply("PostgreSQL") == "Post gress Q L"


def test_a_missing_lexicon_is_an_error_not_a_silent_skip():
    with pytest.raises(tts.TTSError):
        tts.load_lexicon("no_such_lexicon")


# -------------------------------------------------------------- determinism

def test_synthesis_is_byte_identical_across_calls():
    """§11.3. MEASURED: piper's DEFAULT config is not — two calls produced
    different sample counts (120832 vs 125952). SYNTHESIS_PARAMS zeroes the VITS
    noise to fix it, and this test is what stops someone restoring the noise for
    better prosody without noticing what it costs."""
    a = tts.synthesize(SHORT)
    b = tts.synthesize(SHORT)
    assert a.hash == b.hash
    assert a.sample_count == b.sample_count
    assert tts.read_pcm(a.hash) == tts.read_pcm(b.hash)


def test_the_noise_parameters_are_pinned_to_zero():
    assert tts.SYNTHESIS_PARAMS["noise_scale"] == 0.0
    assert tts.SYNTHESIS_PARAMS["noise_w_scale"] == 0.0


def test_audio_comes_out_at_the_pinned_rate():
    """§11.4's 1600-samples-per-frame identity only holds at 48 kHz."""
    a = tts.synthesize(SHORT)
    assert a.sample_rate == rtime.SAMPLE_RATE == 48000
    assert rtime.SAMPLES_PER_FRAME == 1600


# ------------------------------------------------------------------ closure

def test_the_closure_is_stable_for_the_same_inputs():
    """Invariant 1: two scenes with identical narration share one synthesis."""
    lex = tts.load_lexicon("en.v1")
    a = tts.closure(SHORT, voice_id="en_US-lessac-medium", model_id="m", lexicon=lex)
    b = tts.closure(SHORT, voice_id="en_US-lessac-medium", model_id="m", lexicon=lex)
    assert a == b and len(a) == 64


def test_different_text_is_a_different_hash():
    lex = tts.load_lexicon("en.v1")
    a = tts.closure(SHORT, voice_id="en_US-lessac-medium", model_id="m", lexicon=lex)
    b = tts.closure(TWO, voice_id="en_US-lessac-medium", model_id="m", lexicon=lex)
    assert a != b


def test_a_voice_that_is_not_on_disk_is_refused():
    lex = tts.load_lexicon("en.v1")
    with pytest.raises(tts.TTSError):
        tts.closure(SHORT, voice_id="not_a_voice", model_id="m", lexicon=lex)


def test_an_unpinned_voice_is_refused():
    """Invariant 6: pinned in config, never latest."""
    with pytest.raises(tts.TTSError):
        tts.synthesize(SHORT, voice_id="unpinned", model_id="unpinned")


def test_the_second_call_is_a_cache_hit():
    tts.synthesize(SHORT)
    assert tts.synthesize(SHORT).cached


# ---------------------------------------------------------------- alignment

def test_spans_tile_the_audio_exactly():
    a = tts.synthesize(TWO)
    al = A.align("s01", Narration.from_text(TWO), a)
    assert al.spans[0].start == 0
    assert al.spans[-1].end == a.sample_count
    for x, y in zip(al.spans, al.spans[1:]):
        assert x.end == y.start, "a gap here becomes cue drift"


def test_every_span_receives_a_start_and_an_end():
    a = tts.synthesize(TWO)
    n = Narration.from_text(TWO)
    al = A.align("s01", n, a)
    assert {s.span_id for s in al.spans} == {s.id for s in n.spans}
    assert all(s.end > s.start for s in al.spans)


def test_span_timings_are_measured_and_word_timings_are_estimated():
    """§16.1 drives kinetic typography from this sidecar. A consumer that reads
    an estimate as a measurement builds a feature that drifts on long lines."""
    a = tts.synthesize(TWO)
    al = A.align("s01", Narration.from_text(TWO), a)
    assert al.spans[0].method.startswith("measured")
    assert al.spans[0].words[0].method.startswith("estimated")
    doc = al.to_json()
    assert doc["span_method"] != doc["word_method"]


def test_duration_is_derived_from_the_audio():
    """R5: never authored."""
    a = tts.synthesize(TWO)
    al = A.align("s01", Narration.from_text(TWO), a)
    assert al.duration == rtime.RationalTime.from_samples(a.sample_count, 48000)


def test_resolving_a_cue_span_gives_a_time():
    """R3: a cue names a span; this is where that becomes a time."""
    n = Narration.from_text(TWO)
    al = A.align("s01", n, tts.synthesize(TWO))
    assert al.resolve(n.spans[1].id).start_time().value > 0


def test_resolving_an_unknown_span_lists_the_real_ones():
    n = Narration.from_text(TWO)
    al = A.align("s01", n, tts.synthesize(TWO))
    with pytest.raises(A.AlignmentError) as e:
        al.resolve("sp_deadbeef00")
    assert n.spans[0].id in str(e.value)


# ------------------------------------------------ the hard error, ISSUE-11

class FakeAudio:
    def __init__(self, chunks, total):
        self.chunks, self.sample_count = chunks, total
        self.hash, self.sample_rate = "f" * 64, 48000


def test_a_partition_mismatch_is_a_hard_error_not_a_positional_guess():
    """ISSUE-11 exactly. A positional guess would mistime every cue."""
    n = Narration.from_text(TWO)
    with pytest.raises(A.AlignmentError) as e:
        A.align("s05", n, FakeAudio([{"start": 0, "end": 100}], 100))
    assert "2 spans but 1 TTS chunks" in str(e.value)


def test_no_chunks_at_all_is_a_hard_error():
    with pytest.raises(A.AlignmentError) as e:
        A.align("s01", Narration.from_text(SHORT), FakeAudio([], 0))
    assert "no chunk boundaries" in str(e.value)


def test_a_zero_length_span_is_a_hard_error():
    with pytest.raises(A.AlignmentError):
        A.align("s01", Narration.from_text(SHORT),
                FakeAudio([{"start": 0, "end": 0}], 0))


def test_the_per_span_fallback_recovers_a_mismatched_scene():
    """ISSUE-11's workaround: every span still gets a measured start and end,
    and the deviation is reported on the result rather than hidden."""
    from explainer import speech
    text = "SELECT ... FOR UPDATE locks the rows you read. That is the point."
    n = Narration.from_text(text)
    sp = speech.speak("s05", text)
    assert len(sp.alignment.spans) == len(n.spans)
    assert sp.alignment.spans[-1].end == sp.audio.sample_count


# ------------------------------------------------------------ word timings

def test_words_tile_their_span_with_no_gap():
    words = A.distribute_words("one two three four", 1000, 5000)
    assert words[0].start == 1000 and words[-1].end == 5000
    for a, b in zip(words, words[1:]):
        assert a.end == b.start


def test_a_longer_word_gets_more_of_the_interval():
    words = A.distribute_words("a complicated", 0, 10000)
    assert words[1].end - words[1].start > words[0].end - words[0].start


def test_an_empty_span_yields_no_words():
    assert A.distribute_words("   ", 0, 100) == []


def test_word_distribution_is_deterministic():
    a = A.distribute_words("the quick brown fox jumps", 0, 48000)
    b = A.distribute_words("the quick brown fox jumps", 0, 48000)
    assert [w.to_json() for w in a] == [w.to_json() for w in b]

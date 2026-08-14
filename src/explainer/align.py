"""Forced alignment — §16.1, CHALLENGES R3/R4.

Turns one scene's audio into per-span and per-word timings, written back to the
spans. This is what makes R3's span anchoring *resolvable*: a cue anchored to
`sp_88c9f341ee` is meaningless until something says where that span is in time.

## Two levels, and only one of them is measured

**Span boundaries are MEASURED.** piper emits exactly one synthesis chunk per
sentence, and `Narration.from_text` segments on sentence boundaries, so the
chunks and the spans are the same partition of the same text. Each span's start
and end are read off the audio, not estimated. `SPAN_METHOD` records this.

**Word boundaries inside a span are ESTIMATED**, and the sidecar says so on
every word. §16.1's preferred source is TTS-native timestamps, and piper exposes
`phoneme_id_samples` for voices that export alignment outputs — but
`en_US-lessac-medium` does not (MEASURED: `include_alignments=True` returns an
empty list and `phoneme_alignments` is None). §16.1's stated fallback is MFA
3.0, which is not installed here.

So word timings are distributed within their measured span, weighted by a
syllable count that reuses `prose.count_syllables` — the same function the
readability gate uses, so a word that reads long also gets more time.

**Why this distinction is written on every word rather than in a comment:**
§16.1 drives kinetic typography and word-level highlighting from this sidecar.
A consumer that treats an estimate as a measurement will build a feature that
looks right on the demo sentence and drifts on the long ones. Captions are
emitted at SPAN level precisely because that level is exact.

## The hard error

Every span in a scene must receive a start and an end. A span with no alignment
is a hard error, never a warning: an unaligned span is one whose cues cannot
resolve, and continuing would produce a video with silently mistimed signals.
When the chunk count and the span count disagree, this refuses to guess a
mapping rather than aligning them positionally and hoping.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import rtime
from .prose import count_syllables
from .spans import Narration

SPAN_METHOD = "measured:tts_chunk"
WORD_METHOD = "estimated:syllable_weighted"

_WORD_RE = re.compile(r"\S+")


class AlignmentError(RuntimeError):
    """A span could not be given a start and an end. Never downgraded."""


@dataclass
class WordTiming:
    word: str
    start: int          # samples, absolute within the scene
    end: int
    method: str = WORD_METHOD

    def to_json(self) -> dict:
        return {"word": self.word, "start": self.start, "end": self.end,
                "method": self.method}


@dataclass
class SpanTiming:
    span_id: str
    text: str
    start: int          # samples, absolute within the scene
    end: int
    words: list[WordTiming] = field(default_factory=list)
    method: str = SPAN_METHOD

    @property
    def sample_count(self) -> int:
        return self.end - self.start

    def start_time(self) -> rtime.RationalTime:
        return rtime.RationalTime.from_samples(self.start, rtime.SAMPLE_RATE)

    def end_time(self) -> rtime.RationalTime:
        return rtime.RationalTime.from_samples(self.end, rtime.SAMPLE_RATE)

    def to_json(self) -> dict:
        return {"spanId": self.span_id, "text": self.text,
                "start": self.start, "end": self.end, "method": self.method,
                "words": [w.to_json() for w in self.words]}


@dataclass
class SceneAlignment:
    scene_ref: str
    audio_hash: str
    sample_rate: int
    spans: list[SpanTiming] = field(default_factory=list)

    @property
    def sample_count(self) -> int:
        return self.spans[-1].end if self.spans else 0

    @property
    def duration(self) -> rtime.RationalTime:
        """R5. Derived from the audio, never authored."""
        return rtime.RationalTime.from_samples(self.sample_count,
                                               self.sample_rate)

    def by_span(self) -> dict[str, SpanTiming]:
        return {s.span_id: s for s in self.spans}

    def resolve(self, span_id: str) -> SpanTiming:
        """R3: a cue names a span; this is where that becomes a time."""
        found = self.by_span().get(span_id)
        if found is None:
            raise AlignmentError(
                f"{self.scene_ref}: no alignment for span {span_id!r}. Spans in "
                f"this scene: {[s.span_id for s in self.spans]}")
        return found

    def to_json(self) -> dict:
        return {"scene_ref": self.scene_ref, "audio_hash": self.audio_hash,
                "sample_rate": self.sample_rate,
                "span_method": SPAN_METHOD, "word_method": WORD_METHOD,
                "spans": [s.to_json() for s in self.spans]}


# ------------------------------------------------------------------- words

def distribute_words(text: str, start: int, end: int) -> list[WordTiming]:
    """Split one span's measured interval across its words.

    Weighted by syllable count with a floor of 1, so a long word gets more of
    the interval than a short one. Deterministic and exhaustive: the words tile
    the span with no gap, and the last word absorbs the rounding remainder so
    the sum is exactly `end - start`.
    """
    words = _WORD_RE.findall(text)
    if not words:
        return []
    weights = [max(1, count_syllables(w)) for w in words]
    total_weight = sum(weights)
    span_samples = end - start

    out: list[WordTiming] = []
    cursor = start
    for i, (w, weight) in enumerate(zip(words, weights)):
        if i == len(words) - 1:
            w_end = end
        else:
            w_end = cursor + int(round(span_samples * weight / total_weight))
            w_end = min(w_end, end)
        out.append(WordTiming(word=w, start=cursor, end=max(w_end, cursor)))
        cursor = out[-1].end
    return out


# ------------------------------------------------------------------- align

def align(scene_ref: str, narration: Narration, audio) -> SceneAlignment:
    """Span and word timings for one scene. `audio` is a `tts.SceneAudio`.

    Raises `AlignmentError` rather than producing a partial alignment.
    """
    spans = list(narration.spans)
    chunks = list(audio.chunks or [])

    if not spans:
        raise AlignmentError(f"{scene_ref}: scene has no spans to align")
    if not chunks:
        raise AlignmentError(
            f"{scene_ref}: TTS returned no chunk boundaries, so no span can be "
            f"given a start and an end. This is not recoverable by estimation: "
            f"a span with no alignment has cues that cannot resolve.")
    if len(chunks) != len(spans):
        raise AlignmentError(
            f"{scene_ref}: {len(spans)} spans but {len(chunks)} TTS chunks. "
            f"These must be the same partition of the same text — piper emits "
            f"one chunk per sentence and Narration.from_text segments on "
            f"sentence boundaries. A positional guess here would mistime every "
            f"cue in the scene, so it is refused.\n"
            f"  spans:  {[s.text[:40] for s in spans]}\n"
            f"  chunks: {[c.get('phonemes', '')[:24] for c in chunks]}")

    out: list[SpanTiming] = []
    for span, chunk in zip(spans, chunks):
        start, end = int(chunk["start"]), int(chunk["end"])
        if end <= start:
            raise AlignmentError(
                f"{scene_ref}: span {span.id} was allotted {end - start} "
                f"samples. A zero-length span cannot host a cue.")
        out.append(SpanTiming(span_id=span.id, text=span.text,
                              start=start, end=end,
                              words=distribute_words(span.text, start, end)))

    if out[0].start != 0:
        raise AlignmentError(
            f"{scene_ref}: first span starts at sample {out[0].start}, not 0")
    for a, b in zip(out, out[1:]):
        if a.end != b.start:
            raise AlignmentError(
                f"{scene_ref}: gap between {a.span_id} (ends {a.end}) and "
                f"{b.span_id} (starts {b.start}). Spans must tile the audio.")
    if out[-1].end != audio.sample_count:
        raise AlignmentError(
            f"{scene_ref}: spans cover {out[-1].end} samples but the audio is "
            f"{audio.sample_count}")

    return SceneAlignment(scene_ref=scene_ref, audio_hash=audio.hash,
                          sample_rate=audio.sample_rate, spans=out)

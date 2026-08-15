"""Scene audio + alignment as one operation — the join `tts` and `align` need.

Kept out of both modules because it owns two decisions neither should:

1. what to do when the TTS chunk partition and the span partition disagree
   (ISSUE-11);
2. where span identity comes from.

## Span ids come from the database, never from re-segmentation

MEASURED: minting span ids is not stable. Two authoring passes over the same
string return different ids, because they come from `uuid4`:

    author("One two. Three four.") -> sp_86413ddd46
    author("One two. Three four.") -> sp_939670a2cc

So re-deriving a Narration from stored text produces spans that no stored cue
can anchor to. R3 says a cue anchors to a span id; if that id is regenerated on
read, every cue in the video silently fails to resolve — and it fails *quietly*,
because the new ids are still well-formed.

`spans.Narration` now has two constructors instead of one used carefully:
`author()` mints ids at authoring time, `from_stored()` requires them. The old
`from_text` raises. `speak()` takes a Narration and refuses a raw string, so the
render path cannot reach the authoring constructor by accident.

## Why synthesis is per span rather than per scene

The original design synthesised a whole scene in one TTS call and recovered span
boundaries from piper's per-sentence chunking. That works only while two
independent sentence splitters agree, and MEASURED, they do not:

    v2 s05, 7 spans:  each span synthesised ALONE yields exactly 1 chunk
                      all seven synthesised TOGETHER yield 6 chunks

piper's splitter merges differently depending on surrounding context, so the
same span produces a different partition according to what sits next to it.
Fixing `spans.py` (ISSUE-11) removed the ellipsis case and took v2 from 3
mismatched scenes to 1 — but "1 silent misalignment per video" is not a
different class of problem from 3.

So the partition is no longer derived twice and reconciled. **One span in, one
audio part out**, concatenated. The spans and the chunks match because they are
the same list, not because two algorithms happened to agree.

The cost is prosody continuity across a sentence boundary. It is small — piper
already resets prosody at every sentence internally, and spans are sentences —
and it buys the elimination of a failure that is silent, context-dependent, and
mistimes every cue in an affected scene. Recorded as **W5**.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import align as align_mod
from . import tts


@dataclass
class SceneSpeech:
    scene_ref: str
    audio: tts.SceneAudio
    alignment: align_mod.SceneAlignment
    per_span_fallback: bool = False

    @property
    def seconds(self) -> float:
        return self.audio.seconds


def speak(scene_ref: str, narration, **kw) -> SceneSpeech:
    """Synthesise and align one scene.

    `narration` is a `spans.Narration`, normally built
    from the database. A plain string is accepted for tests and one-off checks
    and is segmented on the spot, which is fine only because nothing anchors to
    those ids.

    **Synthesis is per span, by construction.** See the module docstring: two
    independent sentence splitters cannot be relied on to agree, and when they
    disagree every cue in the scene is mistimed. One span in, one audio part
    out, and the partition matches because it was never derived twice.
    """
    if isinstance(narration, str):
        raise TypeError(
            "speak() needs a Narration, not raw text. Build it with "
            "Narration.from_stored(rows) — the render path must never "
            "re-segment stored narration, because that mints new span ids and "
            "orphans every cue (R3).")

    audio = tts.synthesize_spans([s.text for s in narration.spans], **kw)
    alignment = align_mod.align(scene_ref, narration, audio)
    return SceneSpeech(scene_ref, audio, alignment, per_span_fallback=False)

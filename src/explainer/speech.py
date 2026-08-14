"""Scene audio + alignment as one operation — the join `tts` and `align` need.

Kept out of both modules because it owns two decisions neither should:

1. what to do when the TTS chunk partition and the span partition disagree
   (ISSUE-11);
2. where span identity comes from.

## Span ids come from the database, never from re-segmentation

MEASURED: `Narration.from_text` does **not** produce stable span ids. Two calls
on the same string return different ones:

    from_text("One two. Three four.") -> sp_86413ddd46
    from_text("One two. Three four.") -> sp_939670a2cc

So re-deriving a Narration from stored narration text produces spans that no
stored cue can anchor to. R3 says a cue anchors to a span id; if that id is
regenerated on read, every cue in the video silently fails to resolve — and it
fails *quietly*, because the ids are still well-formed.

`StoredNarration` therefore adapts the rows as they were written. Nothing in the
render path may call `from_text` on narration that already exists.
`spans.py` is where authoring happens; this is where reading happens.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import align as align_mod
from . import tts


@dataclass(frozen=True)
class StoredSpan:
    id: str
    text: str


@dataclass(frozen=True)
class StoredNarration:
    """A read-only Narration built from `scenes.narration` rows.

    Duck-types the part of `spans.Narration` that alignment and the signal
    designer use — `.spans`, each with `.id` and `.text` — without re-running
    segmentation, so the ids are the ones cues were authored against.
    """

    spans: tuple[StoredSpan, ...]

    @classmethod
    def from_rows(cls, rows: list[dict]) -> "StoredNarration":
        out = []
        for r in rows or []:
            sid = r.get("id") or r.get("spanId")
            if not sid:
                raise ValueError(
                    f"stored narration row has no span id: {r!r}. R3 anchoring "
                    f"needs it and it cannot be regenerated — from_text is not "
                    f"stable.")
            out.append(StoredSpan(id=sid, text=r.get("text") or ""))
        return cls(spans=tuple(out))

    @property
    def text(self) -> str:
        return " ".join(s.text for s in self.spans)


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

    `narration` is anything with `.spans` — normally a `StoredNarration` built
    from the database. A plain string is accepted for tests and one-off checks
    and is segmented on the spot, which is fine only because nothing anchors to
    those ids.

    Per-scene synthesis first; per-span only when the partitions disagree. The
    fallback is not a silent repair — it is returned on the result, because a
    scene synthesised span by span has different prosody from its neighbours
    and ISSUE-11 says why.
    """
    if isinstance(narration, str):
        from .spans import Narration
        narration = Narration.from_text(narration)

    text = " ".join(s.text for s in narration.spans)
    audio = tts.synthesize(text, **kw)
    try:
        alignment = align_mod.align(scene_ref, narration, audio)
        return SceneSpeech(scene_ref, audio, alignment, per_span_fallback=False)
    except align_mod.AlignmentError:
        # ISSUE-11. Every span must get a start and an end; that requirement
        # outranks the one-call-per-scene preference, and the deviation is
        # reported rather than hidden.
        audio = tts.synthesize_spans([s.text for s in narration.spans], **kw)
        alignment = align_mod.align(scene_ref, narration, audio)
        return SceneSpeech(scene_ref, audio, alignment, per_span_fallback=True)

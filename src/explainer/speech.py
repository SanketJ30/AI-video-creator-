"""Scene audio + alignment as one operation — the join `tts` and `align` need.

Kept out of both modules because it owns a decision neither should: what to do
when the TTS chunk partition and the span partition disagree (ISSUE-11).
"""
from __future__ import annotations

from dataclasses import dataclass

from . import align as align_mod
from . import tts
from .spans import Narration


@dataclass
class SceneSpeech:
    scene_ref: str
    audio: tts.SceneAudio
    alignment: align_mod.SceneAlignment
    per_span_fallback: bool = False

    @property
    def seconds(self) -> float:
        return self.audio.seconds


def speak(scene_ref: str, text: str, **kw) -> SceneSpeech:
    """Synthesise and align one scene. Per-scene first, per-span only if forced.

    The fallback is not a silent repair: it is returned on the result and the
    caller is expected to surface it, because a scene synthesised span by span
    has different prosody from its neighbours and ISSUE-11 says why.
    """
    narration = Narration.from_text(text)
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

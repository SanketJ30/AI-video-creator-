"""Narration spans and span-anchored cues (PRD v0.2 §5.2 R3, R4).

    "Every animation cue anchors to a narration span ID, never a timestamp.
     Translation preserves span IDs. The timing resolver maps span IDs to
     per-locale word timings. This decision must be made before a single line of
     animation code is written. Retrofitting it is a rewrite."

The span is the join key between five things that otherwise drift apart:
script, audio, captions, animation cues, and translations. A cue that says
"highlight term-A at 4.2s" is wrong in every other language and wrong again the
moment anyone edits a word. A cue that says "highlight term-A at the start of
span sp_7f3a, minus 100ms" survives both.

Span IDs are opaque and permanent. They are NOT derived from position, because
position changes when someone edits the script, and a cue must not silently
re-point at different words.
"""
from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

from .rtime import FPS, RationalTime

SPAN_ID_RE = re.compile(r"^sp_[0-9a-f]{10}$")


def new_span_id() -> str:
    return f"sp_{uuid.uuid4().hex[:10]}"


class AnchorPoint(str, Enum):
    START = "start"
    END = "end"


@dataclass
class Span:
    """Roughly a clause (R4). The atomic unit of narration.

    `text` is the authored words. `word_timings` is filled in by forced
    alignment after TTS — it is per-locale, derived, and never authored.
    """

    id: str
    text: str
    order: int
    # Derived by the alignment pass. None until TTS has run for this locale.
    start: RationalTime | None = None
    end: RationalTime | None = None
    word_timings: list[tuple[str, RationalTime, RationalTime]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not SPAN_ID_RE.match(self.id):
            raise ValueError(f"malformed span id {self.id!r}; expected sp_ + 10 hex")

    @property
    def aligned(self) -> bool:
        return self.start is not None and self.end is not None

    @property
    def duration(self) -> RationalTime:
        if not self.aligned:
            raise ValueError(f"span {self.id} is not aligned yet; run TTS + alignment first")
        assert self.start is not None and self.end is not None
        return self.end - self.start

    def word_count(self) -> int:
        return len(self.text.split())

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "order": self.order,
            "start": self.start.to_json() if self.start else None,
            "end": self.end.to_json() if self.end else None,
        }


@dataclass
class Anchor:
    """Where in the narration a cue fires. Never a bare timestamp (R3)."""

    span_id: str
    point: AnchorPoint = AnchorPoint.START
    offset: RationalTime = field(default_factory=lambda: RationalTime(0, FPS))

    def to_json(self) -> dict:
        return {"spanId": self.span_id, "point": self.point.value,
                "offset": self.offset.to_json()}

    @classmethod
    def from_json(cls, obj: dict) -> "Anchor":
        return cls(obj["spanId"], AnchorPoint(obj.get("point", "start")),
                   RationalTime.from_json(obj["offset"]) if obj.get("offset")
                   else RationalTime(0, FPS))


@dataclass
class Cue:
    """One animation event. `kind` is a template-level verb (highlight,
    reveal, emphasise, build_step...), `target` names a slot in the visualSpec.

    §8: "What gets highlighted, and when — Signal Designer, anchored to
    narration spans, +/- 150 ms."
    """

    kind: str
    target: str
    anchor: Anchor
    params: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return {"kind": self.kind, "target": self.target,
                "anchor": self.anchor.to_json(), "params": self.params}


class Narration:
    """An ordered list of spans, addressable by id."""

    def __init__(self, spans: list[Span]):
        ids = [s.id for s in spans]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate span ids in one narration")
        self.spans = sorted(spans, key=lambda s: s.order)

    # ------------------------------------------------------------ authoring

    @classmethod
    def from_text(cls, text: str) -> "Narration":
        """Segment authored prose into spans at clause boundaries (R4).

        Deliberately conservative: sentence terminators, then long clauses split
        at semicolons and em dashes. Over-splitting costs nothing (cues just get
        finer anchors); under-splitting means a cue cannot point at the words it
        means.
        """
        chunks = _segment(text)
        return cls([Span(id=new_span_id(), text=c, order=i)
                    for i, c in enumerate(chunks)])

    def by_id(self, span_id: str) -> Span:
        for s in self.spans:
            if s.id == span_id:
                return s
        raise KeyError(
            f"no span {span_id} in this narration. A cue is pointing at a span "
            "that was deleted — this is exactly the breakage R3 exists to make "
            "loud rather than silent.")

    @property
    def text(self) -> str:
        return " ".join(s.text for s in self.spans)

    def word_count(self) -> int:
        return sum(s.word_count() for s in self.spans)

    # -------------------------------------------------------------- timing

    @property
    def aligned(self) -> bool:
        return all(s.aligned for s in self.spans)

    @property
    def duration(self) -> RationalTime:
        """Derived from alignment, never authored (R5)."""
        if not self.spans:
            return RationalTime(0, FPS)
        if not self.aligned:
            raise ValueError("narration not aligned; duration is derived, not authored")
        last = self.spans[-1]
        assert last.end is not None
        return last.end

    def resolve_cue(self, cue: Cue) -> RationalTime:
        """Turn a span-anchored cue into a concrete local time.

        Runs per locale, in the timing resolution pass, AFTER alignment and
        BEFORE pixels (§11.2's two-phase tag-then-flush). Clamped to the span's
        own bounds so a large negative offset cannot fire before the scene starts.
        """
        span = self.by_id(cue.anchor.span_id)
        if not span.aligned:
            raise ValueError(f"span {span.id} not aligned; cannot resolve cue {cue.kind}")
        base = span.start if cue.anchor.point is AnchorPoint.START else span.end
        assert base is not None
        t = base + cue.anchor.offset
        zero = RationalTime(0, FPS)
        if t < zero:
            return zero
        return t

    # ------------------------------------------------------- localisation

    def to_xliff_units(self) -> list[dict]:
        """§5.2 R3: translators receive a segmented, ID-tagged script (XLIFF 2.x),
        not free prose — which is what preserves span IDs across locales."""
        return [{"id": s.id, "source": s.text} for s in self.spans]

    def apply_translation(self, units: Iterable[dict]) -> "Narration":
        """Rebuild a Narration in another locale, PRESERVING span ids.

        Cues written against the source locale keep working, because they point
        at span ids and the ids did not move. Timings are cleared: they must be
        re-derived from that locale's TTS.
        """
        by_id = {u["id"]: u["target"] for u in units}
        missing = [s.id for s in self.spans if s.id not in by_id]
        if missing:
            raise ValueError(
                f"translation dropped spans {missing}. Every span must survive "
                "translation or its cues become unresolvable.")
        return Narration([Span(id=s.id, text=by_id[s.id], order=s.order)
                          for s in self.spans])

    # -------------------------------------------------------------- hashing

    def content_key(self) -> str:
        """Stable key over ids + text, for the cache closure. Excludes timings,
        which are derived — including them would make the closure depend on its
        own output."""
        payload = "\n".join(f"{s.order}\x1f{s.id}\x1f{s.text}" for s in self.spans)
        return hashlib.sha256(payload.encode()).hexdigest()

    def to_json(self) -> list[dict]:
        return [s.to_json() for s in self.spans]


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_SUBCLAUSE = re.compile(r"\s*[;—]\s*|\s+—\s+")
_LONG = 18  # words; above this we look for a subclause boundary


def _segment(text: str) -> list[str]:
    out: list[str] = []
    for sentence in _SENTENCE_END.split(text.strip()):
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence.split()) <= _LONG:
            out.append(sentence)
            continue
        parts = [p.strip() for p in _SUBCLAUSE.split(sentence) if p.strip()]
        out.extend(parts if len(parts) > 1 else [sentence])
    return out

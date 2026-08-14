"""Span and cue tests (PRD R3, R4).

The property under test: a cue survives a script edit and a translation, because
it points at a span id rather than a timestamp.
"""
import pytest

from explainer.rtime import FPS, RationalTime
from explainer.spans import (Anchor, AnchorPoint, Cue, Narration, Span,
                             new_span_id)

TEXT = ("Two transactions read the same snapshot. Neither sees the other's write, "
        "so both pass the check; the invariant breaks anyway.")


def test_segmentation_produces_spans():
    n = Narration.from_text(TEXT)
    assert len(n.spans) >= 2
    assert all(s.id.startswith("sp_") for s in n.spans)
    assert n.spans == sorted(n.spans, key=lambda s: s.order)


def test_span_ids_are_opaque_not_derived():
    """Ids must not be a function of position or text.

    If they were, editing a word or reordering scenes would mint a new id for the
    same clause, and every cue pointing at it would silently re-target. Two
    segmentations of identical text must therefore produce different ids.
    """
    a = Narration.from_text(TEXT)
    b = Narration.from_text(TEXT)
    assert [s.text for s in a.spans] == [s.text for s in b.spans]
    assert {s.id for s in a.spans}.isdisjoint({s.id for s in b.spans})


def test_span_id_survives_a_text_edit():
    """The complement: editing a span's words keeps its id, so cues hold."""
    n = Narration.from_text(TEXT)
    first = n.spans[0]
    original_id = first.id
    first.text = "Two concurrent transactions read one snapshot."
    assert n.spans[0].id == original_id
    assert n.by_id(original_id).text.startswith("Two concurrent")


def test_malformed_span_id_rejected():
    with pytest.raises(ValueError):
        Span(id="span-1", text="x", order=0)


def test_duplicate_span_ids_rejected():
    sid = new_span_id()
    with pytest.raises(ValueError, match="duplicate"):
        Narration([Span(sid, "a", 0), Span(sid, "b", 1)])


def _align(n: Narration) -> Narration:
    """Stand-in for the forced-alignment pass: 30 frames per span."""
    t = RationalTime(0, FPS)
    for s in n.spans:
        s.start = t
        s.end = t + RationalTime(30, FPS)
        t = s.end
    return n


def test_duration_is_derived_not_authored():
    n = Narration.from_text(TEXT)
    with pytest.raises(ValueError, match="derived"):
        _ = n.duration
    _align(n)
    assert n.duration.frames == 30 * len(n.spans)


def test_cue_resolves_relative_to_its_span():
    n = _align(Narration.from_text(TEXT))
    second = n.spans[1]
    cue = Cue("highlight", "snapshot_b",
              Anchor(second.id, AnchorPoint.START, RationalTime(-3, FPS)))
    assert n.resolve_cue(cue).frames == 27      # 30 - 3


def test_cue_clamped_at_zero():
    n = _align(Narration.from_text(TEXT))
    cue = Cue("reveal", "x", Anchor(n.spans[0].id, AnchorPoint.START,
                                    RationalTime(-60, FPS)))
    assert n.resolve_cue(cue).frames == 0


def test_cue_survives_editing_a_different_span():
    """The core R3 property. Edit span 1; the cue on span 2 still resolves to the
    same place *relative to its own words*."""
    n = _align(Narration.from_text(TEXT))
    target = n.spans[1].id
    cue = Cue("highlight", "t", Anchor(target, AnchorPoint.START))
    n.spans[0].text = "Two concurrent transactions read one snapshot."
    assert n.by_id(target) is n.spans[1]
    assert n.resolve_cue(cue).frames == 30


def test_cue_pointing_at_deleted_span_fails_loudly():
    n = _align(Narration.from_text(TEXT))
    ghost = new_span_id()
    with pytest.raises(KeyError, match="loud"):
        n.resolve_cue(Cue("highlight", "t", Anchor(ghost)))


def test_translation_preserves_span_ids():
    n = Narration.from_text(TEXT)
    units = n.to_xliff_units()
    assert all("id" in u and "source" in u for u in units)
    translated = n.apply_translation(
        [{"id": u["id"], "target": f"[hi] {u['source']}"} for u in units])
    assert [s.id for s in translated.spans] == [s.id for s in n.spans]
    assert not translated.aligned, "translated narration must re-derive its timing"


def test_translation_dropping_a_span_is_rejected():
    n = Narration.from_text(TEXT)
    units = n.to_xliff_units()[:-1]
    with pytest.raises(ValueError, match="dropped"):
        n.apply_translation([{"id": u["id"], "target": u["source"]} for u in units])


def test_content_key_excludes_derived_timings():
    """Timings are derived from TTS; if they entered the cache key, the closure
    would depend on its own output."""
    n = Narration.from_text(TEXT)
    before = n.content_key()
    _align(n)
    assert n.content_key() == before


def test_content_key_changes_with_text():
    a = Narration.from_text(TEXT)
    b = Narration([Span(s.id, s.text, s.order) for s in a.spans])
    assert a.content_key() == b.content_key()
    b.spans[0].text += " Actually not."
    assert b.content_key() != a.content_key()

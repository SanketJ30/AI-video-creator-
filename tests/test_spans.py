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
    n = Narration.author(TEXT)
    assert len(n.spans) >= 2
    assert all(s.id.startswith("sp_") for s in n.spans)
    assert n.spans == sorted(n.spans, key=lambda s: s.order)


def test_span_ids_are_opaque_not_derived():
    """Ids must not be a function of position or text.

    If they were, editing a word or reordering scenes would mint a new id for the
    same clause, and every cue pointing at it would silently re-target. Two
    segmentations of identical text must therefore produce different ids.
    """
    a = Narration.author(TEXT)
    b = Narration.author(TEXT)
    assert [s.text for s in a.spans] == [s.text for s in b.spans]
    assert {s.id for s in a.spans}.isdisjoint({s.id for s in b.spans})


def test_span_id_survives_a_text_edit():
    """The complement: editing a span's words keeps its id, so cues hold."""
    n = Narration.author(TEXT)
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
    n = Narration.author(TEXT)
    with pytest.raises(ValueError, match="derived"):
        _ = n.duration
    _align(n)
    assert n.duration.frames == 30 * len(n.spans)


def test_cue_resolves_relative_to_its_span():
    n = _align(Narration.author(TEXT))
    second = n.spans[1]
    cue = Cue("highlight", "snapshot_b",
              Anchor(second.id, AnchorPoint.START, RationalTime(-3, FPS)))
    assert n.resolve_cue(cue).frames == 27      # 30 - 3


def test_cue_clamped_at_zero():
    n = _align(Narration.author(TEXT))
    cue = Cue("reveal", "x", Anchor(n.spans[0].id, AnchorPoint.START,
                                    RationalTime(-60, FPS)))
    assert n.resolve_cue(cue).frames == 0


def test_cue_survives_editing_a_different_span():
    """The core R3 property. Edit span 1; the cue on span 2 still resolves to the
    same place *relative to its own words*."""
    n = _align(Narration.author(TEXT))
    target = n.spans[1].id
    cue = Cue("highlight", "t", Anchor(target, AnchorPoint.START))
    n.spans[0].text = "Two concurrent transactions read one snapshot."
    assert n.by_id(target) is n.spans[1]
    assert n.resolve_cue(cue).frames == 30


def test_cue_pointing_at_deleted_span_fails_loudly():
    n = _align(Narration.author(TEXT))
    ghost = new_span_id()
    with pytest.raises(KeyError, match="loud"):
        n.resolve_cue(Cue("highlight", "t", Anchor(ghost)))


def test_translation_preserves_span_ids():
    n = Narration.author(TEXT)
    units = n.to_xliff_units()
    assert all("id" in u and "source" in u for u in units)
    translated = n.apply_translation(
        [{"id": u["id"], "target": f"[hi] {u['source']}"} for u in units])
    assert [s.id for s in translated.spans] == [s.id for s in n.spans]
    assert not translated.aligned, "translated narration must re-derive its timing"


def test_translation_dropping_a_span_is_rejected():
    n = Narration.author(TEXT)
    units = n.to_xliff_units()[:-1]
    with pytest.raises(ValueError, match="dropped"):
        n.apply_translation([{"id": u["id"], "target": u["source"]} for u in units])


def test_content_key_excludes_derived_timings():
    """Timings are derived from TTS; if they entered the cache key, the closure
    would depend on its own output."""
    n = Narration.author(TEXT)
    before = n.content_key()
    _align(n)
    assert n.content_key() == before


def test_content_key_changes_with_text():
    a = Narration.author(TEXT)
    b = Narration([Span(s.id, s.text, s.order) for s in a.spans])
    assert a.content_key() == b.content_key()
    b.spans[0].text += " Actually not."
    assert b.content_key() != a.content_key()


# ============================================================ ISSUE-11
#
# Not every full stop ends a sentence. The naive splitter cut
# `SELECT ... FOR UPDATE` in half on real narration, which put a cue anchor and
# a TTS utterance on half a phrase and forced 3 of 9 v2 scenes onto a per-span
# synthesis fallback.

def test_an_ellipsis_does_not_end_a_sentence():
    """The exact string that broke v2 s05."""
    spans = Narration.author(
        "SELECT ... FOR UPDATE locks the rows you read. That is the point.")
    assert [s.text for s in spans.spans] == [
        "SELECT ... FOR UPDATE locks the rows you read.",
        "That is the point."]


def test_i_e_does_not_end_a_sentence():
    spans = Narration.author(
        "Use a lock, i.e. the pessimistic option, before you read.")
    assert len(spans.spans) == 1


def test_e_g_does_not_end_a_sentence():
    spans = Narration.author(
        "Some anomalies, e.g. write skew, slip past Repeatable Read.")
    assert len(spans.spans) == 1


def test_a_decimal_number_does_not_end_a_sentence():
    spans = Narration.author("Set work_mem to 1.5 GB before you run this.")
    assert len(spans.spans) == 1


def test_a_version_number_does_not_end_a_sentence():
    spans = Narration.author(
        "Postgres 16.2 changed the planner. Version 15 did not.")
    assert len(spans.spans) == 2


def test_real_sentence_boundaries_still_split():
    """The fix must not buy correctness by refusing to split at all."""
    spans = Narration.author(
        "Two doctors are on call. Both go off duty. Nobody is left.")
    assert len(spans.spans) == 3


def test_masking_leaves_the_text_byte_identical():
    """The mask is an internal device; no authored character may survive it."""
    text = "SELECT ... FOR UPDATE at 1.5 GB, i.e. plenty. Then commit."
    joined = " ".join(s.text for s in Narration.author(text).spans)
    assert joined == text
    assert "\x00" not in joined


# =========================================== R3: two constructors, not one

def test_the_authoring_constructor_mints_ids():
    a = Narration.author("One two. Three four.")
    b = Narration.author("One two. Three four.")
    assert [s.id for s in a.spans] != [s.id for s in b.spans], (
        "ids come from uuid4; this instability is exactly why re-deriving "
        "spans from stored text orphans every cue")


def test_from_stored_preserves_the_ids_it_is_given():
    rows = [{"id": "sp_1111111111", "text": "One two."},
            {"id": "sp_2222222222", "text": "Three four."}]
    n = Narration.from_stored(rows)
    assert [s.id for s in n.spans] == ["sp_1111111111", "sp_2222222222"]
    assert [s.text for s in n.spans] == ["One two.", "Three four."]


def test_from_stored_does_not_resegment():
    """One stored row is one span, whatever its punctuation. Re-segmenting on
    read would change the span count and orphan cues on the extras."""
    n = Narration.from_stored(
        [{"id": "sp_1111111111", "text": "One. Two. Three."}])
    assert len(n.spans) == 1


def test_from_stored_accepts_the_serialised_key_too():
    n = Narration.from_stored([{"spanId": "sp_3333333333", "text": "x"}])
    assert n.spans[0].id == "sp_3333333333"


def test_from_stored_refuses_a_row_with_no_id():
    """An id that cannot be recovered is data loss, not a defaulting problem."""
    with pytest.raises(ValueError) as e:
        Narration.from_stored([{"text": "no id here"}])
    assert "cannot be regenerated" in str(e.value)


def test_from_text_is_removed_and_says_which_path_to_use():
    """It was one method doing two jobs, and the render path picked the wrong
    one. A comment did not stop that; an exception does."""
    with pytest.raises(TypeError) as e:
        Narration.from_text("One two.")
    msg = str(e.value)
    assert "Narration.author" in msg and "Narration.from_stored" in msg


# ============================ the render path may not mint span ids

def test_no_render_path_module_calls_the_authoring_constructor():
    """R3's structural guard.

    Minting a span id anywhere downstream of authoring orphans every cue that
    points at the old one, and does it silently because the new ids are
    well-formed. This asserts the property rather than trusting review.
    """
    import pathlib
    render_path = ["render.py", "assembly.py", "resolver.py", "align.py",
                   "speech.py", "tts.py"]
    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "explainer"
    offenders = []
    for name in render_path:
        src = (root / name).read_text(encoding="utf-8")
        code = "\n".join(line for line in src.splitlines()
                         if not line.lstrip().startswith("#"))
        # Strip the module docstring, where these names are discussed.
        body = code.split('"""', 2)[-1] if code.count('"""') >= 2 else code
        if "Narration.author(" in body or "new_span_id(" in body:
            offenders.append(name)
    assert not offenders, (
        f"{offenders} mint span ids; only the authoring path may. Use "
        f"Narration.from_stored(rows).")

"""The template registry — §4.4, §8, §9.3, §11.6, §16.2, CHALLENGES R8.

Structure only. Nothing here asserts a template looks good; it asserts the
registry is well formed and that the two properties CHALLENGES calls
irreversible — caption safe area and renderer-agnosticism — hold on every row.
"""
from __future__ import annotations

import pytest

from explainer import templates
from explainer.templates import CAPTION_SAFE_BOTTOM, MIN_FONT_PX, Kind, ParamType

ALL = sorted(templates.TEMPLATES)


def test_the_registry_holds_its_invariants():
    problems = templates.check_registry()
    assert not problems, "; ".join(problems)


@pytest.mark.parametrize("name", ALL)
def test_every_template_declares_a_caption_safe_area(name):
    """§16.2: 'reserve the bottom 15% as a caption exclusion zone in every
    layout template'. CHALLENGES lists retrofitting this as irreversible."""
    t = templates.get(name)
    assert t.safe_area.bottom >= CAPTION_SAFE_BOTTOM


@pytest.mark.parametrize("name", ALL)
def test_no_template_min_duration_exceeds_its_max(name):
    t = templates.get(name)
    assert t.min_sec <= t.max_sec


@pytest.mark.parametrize("name", ALL)
def test_every_template_is_renderer_agnostic(name):
    """R8. A concrete engine name here would be the coupling that makes a
    second renderer a rewrite."""
    assert templates.get(name).renderer == "agnostic"


@pytest.mark.parametrize("name", ALL)
def test_every_template_respects_the_font_floor(name):
    """§11.6: '>=24 px minimum font at 1080p'."""
    assert templates.get(name).min_font_px >= MIN_FONT_PX


@pytest.mark.parametrize("name", ALL)
def test_every_template_has_parameters(name):
    assert templates.get(name).params


@pytest.mark.parametrize("name", ALL)
def test_parameter_names_are_unique_within_a_template(name):
    got = templates.get(name).param_names()
    assert len(got) == len(set(got))


def test_every_section_4_4_composition_type_has_a_template():
    """§4.4 names the on-screen content types. A kind with no template means
    the planner has nothing to select for that composition."""
    for kind in Kind:
        assert templates.by_kind(kind), f"no template of kind {kind.value}"


def test_the_usable_height_accounts_for_the_reserved_band():
    t = templates.get("labelled_diagram")
    assert t.safe_area.usable_height == round(1.0 - CAPTION_SAFE_BOTTOM, 6)


# ------------------------------------------------------- selection helpers

def test_fitting_filters_by_duration_band():
    fits = {t.name for t in templates.fitting(90)}
    assert "labelled_diagram" in fits          # 8-120
    assert "key_phrase" not in fits            # 3-20


def test_every_template_supports_signalling_by_default():
    """ISSUE-13. §9.2 states 'never zero' without exceptions, so the default is
    that the rule applies. An exemption is now an explicit, justified override
    rather than a boolean nobody had to defend."""
    fits = templates.fitting(15, signalling=True)
    assert all(t.supports_signalling for t in fits)
    assert {"labelled_diagram", "key_phrase"} <= {t.name for t in fits}
    assert all(t.supports_signalling for t in templates.TEMPLATES.values())


def test_an_exemption_must_state_a_reason_a_reviewer_can_argue_with():
    import dataclasses
    original = templates.TEMPLATES["key_phrase"]
    try:
        templates.TEMPLATES["key_phrase"] = dataclasses.replace(
            original, signalling_exemption="nope")
        problems = templates.check_registry()
        assert problems and "must say WHY" in problems[0]
    finally:
        templates.TEMPLATES["key_phrase"] = original


def test_an_unknown_template_lists_the_known_ones():
    with pytest.raises(templates.TemplateError) as e:
        templates.get("remotion_diagram_reveal")
    assert "labelled_diagram" in str(e.value)


# ------------------------------------------------------------- validation

def test_a_correctly_filled_template_validates():
    t = templates.get("labelled_diagram")
    assert not templates.validate_params(t, {
        "nodes": [{"id": "n1", "label": "row version"}],
        "edges": [{"from": "n1", "to": "n1", "label": "xmax"}],
        "focus": "n1"})


def test_a_missing_required_parameter_is_reported():
    t = templates.get("key_phrase")
    problems = templates.validate_params(t, {})
    assert any("'phrase' is required" in p for p in problems)


def test_an_optional_parameter_may_be_absent():
    t = templates.get("key_phrase")
    assert not templates.validate_params(t, {"phrase": "snapshot, frozen"})


def test_an_unknown_parameter_is_reported():
    t = templates.get("key_phrase")
    problems = templates.validate_params(t, {"phrase": "x", "fontFamily": "Inter"})
    assert any("unknown parameter 'fontFamily'" in p for p in problems)


def test_exceeding_max_items_is_reported_with_the_reason():
    """§9.3 caps simultaneous on-screen objects at 7, and 4 if any carry text."""
    t = templates.get("labelled_diagram")
    problems = templates.validate_params(t, {
        "nodes": [{"id": f"n{i}", "label": str(i)} for i in range(9)]})
    assert any("more than the 7" in p for p in problems)


def test_an_enum_outside_its_choices_is_reported():
    t = templates.get("series_build")
    problems = templates.validate_params(t, {
        "chart": "sankey", "series": [{"label": "a", "value": 1}]})
    assert any("not one of" in p for p in problems)


def test_a_list_parameter_given_a_scalar_is_reported():
    t = templates.get("labelled_diagram")
    problems = templates.validate_params(t, {"nodes": "n1"})
    assert any("must be a list" in p for p in problems)


def test_an_int_parameter_rejects_a_bool():
    t = templates.get("table_build")
    problems = templates.validate_params(t, {
        "columns": ["a"], "rows": ["b"], "highlight_row": True})
    assert any("must be an int" in p for p in problems)


# ------------------------------------------------- renderer-agnostic shapes

@pytest.mark.parametrize("name", ALL)
def test_no_parameter_names_a_rendering_construct(name):
    """R8 is easy to break by naming a component or a CSS property in a schema.
    This is a crude guard, and crude is the point: it fires on the obvious
    mistakes rather than pretending to understand intent."""
    banned = ("component", "jsx", "css", "className", "style", "remotion",
              "fontfamily", "tailwind", "svg", "div")
    for p in templates.get(name).params:
        lowered = p.name.lower()
        assert not any(b in lowered for b in banned), \
            f"{name}.{p.name} names a rendering construct"


@pytest.mark.parametrize("name", ALL)
def test_parameter_types_are_all_declared(name):
    for p in templates.get(name).params:
        assert isinstance(p.type, ParamType)


# --------------------------------------- D2: on_screen must fail loud, not quiet

def test_a_new_text_parameter_counts_as_on_screen_unless_it_says_otherwise():
    """D2. The default has to be True: a genuine caption param on a future
    template must not silently escape §9.4's on-screen-text share. Opting OUT is
    the deliberate act; opting in is the default."""
    p = templates.Param("caption", ParamType.TEXT)
    assert p.on_screen is True


def test_exactly_the_two_reviewed_parameters_opt_out():
    """Every `on_screen=False` is an authored judgement (D2, week4-decisions).
    If a third appears, it was not reviewed — so this fails and asks for it."""
    opted_out = {(t.name, p.name) for t in templates.TEMPLATES.values() for p in t.params
                 if not p.on_screen}
    assert opted_out == {("cold_open", "premise"),
                         ("concept_illustration", "subject")}


def test_no_asset_or_enum_parameter_needs_the_flag():
    """asset_ref/enum/int are excluded by TYPE, so setting on_screen on them
    would be a second mechanism doing the same job — and two mechanisms is how
    they drift apart."""
    for t in templates.TEMPLATES.values():
        for p in t.params:
            if p.type in (ParamType.ASSET_REF, ParamType.ENUM,
                          ParamType.INT):
                assert p.on_screen is True, (
                    f"{t.name}.{p.name}: excluded by type already")


# ============================= the three shapes the renderer depends on

def test_a_table_row_must_carry_one_cell_per_column():
    """Rows were TEXT_LIST, so the model packed every column into one string
    with '|' separators, the renderer drew one full-width line, and the column
    headers aligned with nothing."""
    t = templates.get("table_build")
    packed = templates.validate_params(
        t, {"columns": ["A", "B"], "rows": ["A | B"]})
    assert packed and "no columns" in packed[0]


def test_a_row_with_the_wrong_cell_count_is_reported():
    t = templates.get("table_build")
    problems = templates.validate_params(
        t, {"columns": ["A", "B", "C"], "rows": [{"cells": ["a", "b"]}]})
    assert problems and "2 cell(s) but there are 3 column(s)" in problems[0]


def test_a_well_formed_table_passes():
    t = templates.get("table_build")
    assert not templates.validate_params(
        t, {"columns": ["A", "B"], "rows": [{"cells": ["a", "b"]},
                                            {"cells": ["c", "d"]}]})


def test_a_timeline_step_must_name_its_lane():
    """Without a track the renderer cannot place a step, and the template stops
    showing the parallelism it exists for."""
    t = templates.get("state_timeline")
    problems = templates.validate_params(
        t, {"tracks": ["Alex", "Bo"], "steps": [{"label": "reads"}]})
    assert problems and "no `track`" in problems[0]


def test_a_step_on_an_unknown_track_is_reported():
    t = templates.get("state_timeline")
    problems = templates.validate_params(
        t, {"tracks": ["Alex", "Bo"],
            "steps": [{"label": "reads", "track": "Carol"}]})
    assert problems and "not one of" in problems[0]


def test_a_well_formed_timeline_passes():
    t = templates.get("state_timeline")
    assert not templates.validate_params(
        t, {"tracks": ["Alex", "Bo"],
            "steps": [{"label": "reads", "track": "Alex"},
                      {"label": "reads", "track": "Bo"}]})


def test_cold_open_requires_a_headline():
    """It has no other on-screen slot, so without this it renders a blank
    frame — measured at 0.00% ink across three v2 scenes."""
    t = templates.get("cold_open")
    assert templates.validate_params(t, {"premise": "two doctors"})
    assert not templates.validate_params(
        t, {"premise": "two doctors", "headline": "Nobody on call"})


def test_every_template_has_at_least_one_on_screen_slot():
    """A template that cannot draw anything is one the planner should not be
    able to choose."""
    for t in templates.TEMPLATES.values():
        drawable = [p for p in t.params
                    if p.on_screen or p.type is ParamType.ASSET_REF]
        assert drawable, f"{t.name} has no slot that puts anything on screen"


def test_kinetic_typography_carries_its_word_timing_precondition():
    """W3: §16.1 drives per-word highlighting from the word sidecar, and those
    timings are ESTIMATED. The constraint lives on the template it constrains
    rather than in a findings doc nobody opens while editing it."""
    t = templates.get("key_phrase")
    assert t.kind is Kind.KINETIC_TYPE
    assert t.preconditions, "the kinetic-type template must state it"
    joined = " ".join(t.preconditions)
    assert "estimated" in joined and "W3" in joined


def test_preconditions_do_not_block_a_render():
    """They are standing notes, not validation. A precondition that silently
    failed a render would be the ISSUE-13 failure shape again."""
    t = templates.get("key_phrase")
    assert not templates.validate_params(t, {"phrase": "Spot it.",
                                             "emphasis": "Spot"})


# ------------------------------------ §15.3: rigid is a template property

def test_no_template_currently_claims_an_intrinsic_tempo():
    """MEASURED: every animation in Scene.tsx is a pure function of
    `progress = frame / (durationInFrames - 1)`, so every template stretches to
    whatever duration it is given. If this fails, a template gained real beats
    and its `rigid` is now earned — check Scene.tsx before changing the test."""
    assert not [t.name for t in templates.TEMPLATES.values() if t.intrinsic_tempo]


def test_rigid_is_downgraded_on_a_template_with_no_tempo():
    """s04 held 15.49s of silence — 17% against §15.3's 15% — to protect a tempo
    that does not exist."""
    got, why = templates.effective_timing_sensitivity("state_timeline", "rigid")
    assert got == "elastic"
    assert "no intrinsic tempo" in why


def test_the_downgrade_is_never_silent():
    """It changes the scene's duration, so a human must see why."""
    _, why = templates.effective_timing_sensitivity("table_build", "rigid")
    assert why and "§15.3" in why


def test_elastic_passes_through_untouched():
    assert templates.effective_timing_sensitivity("key_phrase", "elastic") == (
        "elastic", "")


def test_rigid_survives_on_a_template_that_earns_it():
    """The mechanism must actually permit rigid, or it is just a ban."""
    import dataclasses
    original = templates.TEMPLATES["state_timeline"]
    try:
        templates.TEMPLATES["state_timeline"] = dataclasses.replace(
            original, intrinsic_tempo=True)
        assert templates.effective_timing_sensitivity(
            "state_timeline", "rigid") == ("rigid", "")
    finally:
        templates.TEMPLATES["state_timeline"] = original


def test_an_unknown_template_cannot_claim_a_tempo():
    got, why = templates.effective_timing_sensitivity("no_such", "rigid")
    assert got == "elastic" and "unknown" in why


# ================== ISSUE-20: undesigned templates are not selectable

def test_only_designed_templates_are_offered_to_the_planner():
    """§9 designs six; the registry holds eleven. An undesigned template renders
    legibly but its composition was improvised, and the planner was being shown
    all eleven — MEASURED: `labelled_diagram` was selected on this course two
    storyboard runs ago."""
    assert {t.name for t in templates.selectable()} == {
        "cold_open", "title_card", "key_phrase", "state_timeline",
        "table_build", "concept_illustration"}


def test_every_selectable_template_names_its_design_section():
    for t in templates.selectable():
        assert t.design_section.startswith("§9."), (
            f"{t.name} is selectable but names no design section")


def test_the_undesigned_five_are_named_rather_than_deleted():
    """A gate, not a deletion: they keep their schemas, validation and
    renderers, and each is re-enabled by filling in one field."""
    assert {t.name for t in templates.undesigned()} == {
        "labelled_diagram", "series_build", "term_card", "terminal_replay",
        "ui_walkthrough"}
    for t in templates.undesigned():
        assert t.params, f"{t.name} kept its schema"


def test_the_planner_catalog_excludes_the_undesigned():
    """The risk is a layout nobody reviewed shipping in a video. The model
    cannot choose what it is not shown."""
    import inspect
    from explainer.agents import visual_planner
    src = inspect.getsource(visual_planner)
    assert "templates.selectable()" in src
    assert "sorted(templates.TEMPLATES.values()" not in src


def test_choosing_an_undesigned_template_is_rejected():
    """Belt and braces: even if one reached the parser, it does not pass."""
    import inspect
    from explainer.agents import visual_planner
    assert "has no designed layout" in inspect.getsource(visual_planner)

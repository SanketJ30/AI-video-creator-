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


def test_fitting_can_require_signalling_support():
    """§9.2 wants 1-3 signalling events per scene; a template that cannot host
    a cue constrains what the signal designer may do."""
    fits = templates.fitting(15, signalling=True)
    assert all(t.supports_signalling for t in fits)
    assert "labelled_diagram" in {t.name for t in fits}
    assert "key_phrase" not in {t.name for t in fits}


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

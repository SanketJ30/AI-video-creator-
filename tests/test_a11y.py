"""The accessibility linter — §16.2, WCAG 2.2.

The contrast tests assert against WCAG's own published values rather than
against whatever this implementation happens to return: 21:1 for black on
white, and the two greys either side of the 4.5:1 boundary that every WCAG
tutorial uses (#767676 passes at 4.54, #777777 fails at 4.48). If the maths
drifts, those numbers catch it; a self-consistent fixture would not.

Every other fixture was MEASURED before its assertion was written.
"""
from __future__ import annotations

import pytest

from explainer import a11y as A
from explainer import linter as L
from explainer import templates as T

NARR = "The old version keeps its xmin while a new version gets a fresh one."


def scene(ref="s01", template="labelled_diagram", narration=NARR, spec=None):
    base = {"template": template,
            "slots": {"nodes": [{"id": "a", "label": "old"}]},
            "cues": [{}],
            "captionSafeArea": {"bottom": 0.15}}
    base.update(spec or {})
    return L.SceneView(ref=ref, gagne_slot="present", narration_text=narration,
                       visual_spec=base,
                       pedagogy_meta={"duration_target_seconds": 60})


# ------------------------------------------------------- WCAG contrast math

def test_black_on_white_is_the_published_maximum():
    assert A.contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0)


def test_a_colour_against_itself_is_one_to_one():
    assert A.contrast_ratio("#3a7bd5", "#3a7bd5") == pytest.approx(1.0)


def test_the_ratio_is_order_independent():
    assert (A.contrast_ratio("#000000", "#ffffff")
            == A.contrast_ratio("#ffffff", "#000000"))


def test_the_grey_either_side_of_the_aa_boundary():
    """WCAG's own worked example: #767676 is the darkest grey that passes 4.5:1
    on white, and one step lighter fails."""
    assert A.contrast_ratio("#767676", "#ffffff") == pytest.approx(4.54, abs=0.01)
    assert A.contrast_ratio("#777777", "#ffffff") == pytest.approx(4.48, abs=0.01)
    assert A.contrast_ratio("#767676", "#ffffff") >= A.CONTRAST_NORMAL
    assert A.contrast_ratio("#777777", "#ffffff") < A.CONTRAST_NORMAL


def test_relative_luminance_endpoints():
    assert A.relative_luminance("#ffffff") == pytest.approx(1.0)
    assert A.relative_luminance("#000000") == pytest.approx(0.0)


def test_luminance_uses_the_gamma_curve_not_the_raw_channel():
    """Mid-grey #808080 is 50% in sRGB but 21.6% in luminance. A linear
    implementation would return ~0.5 and silently pass failing contrast."""
    assert A.relative_luminance("#808080") == pytest.approx(0.2159, abs=0.001)


def test_a_colour_that_is_not_six_hex_digits_is_rejected():
    for bad in ("red", "rgb(0,0,0)", "#fff", "", None):
        with pytest.raises(ValueError):
            A.parse_colour(bad)


def test_the_hash_is_optional():
    assert A.parse_colour("ff8800") == A.parse_colour("#ff8800") == (255, 136, 0)


# ----------------------------------------------------- the large-text boundary

def test_eighteen_point_is_large_and_a_hair_under_is_not():
    assert A.is_large_text(18.0)
    assert not A.is_large_text(17.9)


def test_bold_gets_the_lower_boundary():
    assert A.is_large_text(14.0, bold=True)
    assert not A.is_large_text(14.0, bold=False)


def test_large_text_needs_three_to_one_and_normal_needs_four_point_five():
    assert A.required_contrast(18.0) == 3.0
    assert A.required_contrast(12.0) == 4.5


def test_the_registry_minimum_is_exactly_the_wcag_large_text_boundary():
    """§11.6's 24px and WCAG's 18pt are the same size (1pt = 4/3 px), so at the
    registry minimum every text layer is already 'large' and the threshold that
    applies is 3:1. Raising MIN_FONT_PX is safe; LOWERING it silently moves
    every layer to the stricter 4.5:1."""
    assert A.px_to_pt(T.MIN_FONT_PX) == pytest.approx(A.LARGE_PT)
    assert A.required_contrast(A.px_to_pt(T.MIN_FONT_PX)) == A.CONTRAST_LARGE


def test_the_caption_zone_is_one_number_in_two_modules():
    assert A.CAPTION_EXCLUSION_BOTTOM == T.CAPTION_SAFE_BOTTOM == 0.15


# -------------------------------------------------------- contrast as a rule

PALETTE = {"ink": "#111111", "paper": "#ffffff", "muted": "#949494"}


def test_no_palette_reports_unresolved_rather_than_passing():
    """§4.3 makes the report customer-visible. A silent absence would read as
    compliance."""
    found = A.check_contrast("s01", [], palette=None)
    assert len(found) == 1
    assert found[0].rule == "contrast_unresolved"
    assert found[0].severity == "info"
    assert found[0].measured["palette"] is None


def test_a_failing_text_layer_is_blocking():
    """MEASURED: #949494 on white is 3.03:1 — fine for large text, and this
    layer is 12pt, so 4.5:1 applies."""
    found = A.check_contrast(
        "s01", [{"name": "caption", "colour": "muted", "background": "paper",
                 "pt": 12.0}], PALETTE)
    assert len(found) == 1
    assert found[0].rule == "contrast_ratio" and found[0].severity == "blocking"
    assert found[0].measured["ratio"] == pytest.approx(3.03, abs=0.01)
    assert found[0].threshold["min_ratio"] == 4.5


def test_the_same_layer_passes_once_it_is_large():
    """MEASURED: 3.03:1 clears the 3:1 large-text bar. Same colours, same
    ratio, different obligation — which is why size has to be in the check."""
    assert not A.check_contrast(
        "s01", [{"name": "heading", "colour": "muted", "background": "paper",
                 "pt": 18.0}], PALETTE)


def test_a_non_text_graphic_gets_the_three_to_one_bar():
    """§16.2 1.4.11 — 'applies to diagrams, arrows, chart elements', which is
    most of what this engine draws."""
    assert not A.check_contrast(
        "s01", [{"name": "arrow", "colour": "muted", "background": "paper",
                 "non_text": True}], PALETTE)
    found = A.check_contrast(
        "s01", [{"name": "arrow", "colour": "#c8c8c8", "background": "paper",
                 "non_text": True}], PALETTE)
    assert found and found[0].measured["kind"] == "non-text"


def test_a_layer_may_name_a_colour_directly_or_through_the_palette():
    by_name = A.check_contrast("s01", [{"name": "t", "colour": "muted",
                                        "background": "paper", "pt": 12.0}],
                               PALETTE)
    by_hex = A.check_contrast("s01", [{"name": "t", "colour": "#949494",
                                       "background": "#ffffff", "pt": 12.0}],
                              PALETTE)
    assert by_name[0].measured["ratio"] == by_hex[0].measured["ratio"]


def test_a_layer_with_no_size_is_judged_at_the_registry_minimum():
    """Silence means the template's own minimum, not the strictest bar."""
    assert not A.check_contrast(
        "s01", [{"name": "label", "colour": "muted", "background": "paper"}],
        PALETTE)


# ------------------------------------------------------ PEAT / Harding flash

def test_three_transitions_in_a_second_pass_and_four_fail():
    """§16.2's wording is 'fail >3 transitions/s', so 3 is compliant. Off by
    one here is the difference between shipping a seizure risk and blocking a
    clean video."""
    three = [0.0, 0.5, 0.0, 0.5] + [0.5] * 16
    four = [0.0, 0.5, 0.0, 0.5, 0.0] + [0.0] * 15
    assert A.flash_windows(three, [1.0] * 20, fps=10) == []
    assert len(A.flash_windows(four, [1.0] * 20, fps=10)) == 1


def test_a_flash_over_a_small_area_does_not_fail():
    """§16.2 qualifies the criterion with 'over >25% of frame'. A blinking
    cursor is not a seizure risk."""
    lum = [0.0, 0.5] * 10
    assert A.flash_windows(lum, [0.10] * 20, fps=10) == []
    assert A.flash_windows(lum, [0.80] * 20, fps=10)


def test_a_bright_flash_between_two_light_states_does_not_count():
    """PEAT's general flash definition requires the darker state below 0.80 —
    a shimmer between two near-whites is not a flash."""
    lum = [0.85, 0.98] * 10
    assert A.flash_windows(lum, [1.0] * 20, fps=10) == []


def test_a_still_frame_sequence_is_clean():
    assert A.flash_windows([0.4] * 60, [0.0] * 60, fps=30) == []


def test_overlapping_windows_collapse_to_one_finding_per_burst():
    """A 4-transition burst fails every window containing it; a human wants one
    line, not ten."""
    lum = [0.0, 0.5, 0.0, 0.5, 0.0] + [0.0] * 25
    out = A.flash_windows(lum, [1.0] * 30, fps=10)
    assert len(out) == 1 and out[0].transitions == 4


def test_flash_findings_are_blocking_and_carry_the_second():
    lum = [0.0, 0.5] * 10
    found = A.flash_findings("s01", lum, [1.0] * 20, fps=10)
    assert found and all(f.severity == "blocking" for f in found)
    assert "at_second" in found[0].measured


def test_mismatched_frame_series_is_an_error_not_a_silent_truncation():
    with pytest.raises(ValueError):
        A.flash_windows([0.1, 0.2, 0.3], [1.0, 1.0], fps=10)


def test_zero_fps_is_rejected():
    with pytest.raises(ValueError):
        A.flash_windows([0.1, 0.2], [1.0, 1.0], fps=0)


# ------------------------------------------------------------- scene rules

def test_a_scene_with_no_narration_cannot_be_captioned():
    found = A.check_caption_presence("s01", "   ")
    assert found and found[0].severity == "blocking"
    assert found[0].rule == "caption_impossible"


def test_a_narrated_scene_passes_caption_presence():
    assert not A.check_caption_presence("s01", NARR)


def test_a_silent_screen_capture_needs_a_transcript():
    """§16.2 1.2.1. ui_walkthrough is the only SCREEN_DEMO in the registry."""
    t = T.get("ui_walkthrough")
    assert t.kind is T.Kind.SCREEN_DEMO
    found = A.check_silent_screen_capture("s01", t, "")
    assert found and found[0].rule == "silent_screen_capture"


def test_a_narrated_screen_capture_is_fine():
    assert not A.check_silent_screen_capture("s01", T.get("ui_walkthrough"), NARR)


def test_a_silent_non_screen_capture_is_not_this_rule_s_problem():
    """It is caption_impossible's problem, and reporting it twice helps nobody."""
    assert not A.check_silent_screen_capture("s01", T.get("key_phrase"), "")


def test_a_scene_shrinking_type_below_the_minimum_is_blocking():
    found = A.check_font_size("s01", T.get("key_phrase"), {"font_px": 20})
    assert found and found[0].severity == "blocking"
    assert found[0].measured["font_px"] == 20
    assert found[0].threshold["min_font_px"] == 24


def test_a_scene_that_does_not_override_inherits_the_template_minimum():
    assert not A.check_font_size("s01", T.get("key_phrase"), {})
    assert not A.check_font_size("s01", T.get("key_phrase"), None)


def test_every_registered_template_meets_the_font_minimum():
    """Belt and braces with templates.check_registry — this is the rule §11.6
    actually states, and it should hold on real data, not just fixtures."""
    for t in T.TEMPLATES.values():
        assert not A.check_font_size("s", t, None), t.name


def test_a_scene_reserving_less_than_fifteen_percent_is_blocking():
    found = A.check_caption_exclusion(
        "s01", T.get("labelled_diagram"), {"captionSafeArea": {"bottom": 0.08}})
    assert found and found[0].severity == "blocking"
    assert found[0].measured["reserved_bottom"] == 0.08


def test_every_registered_template_reserves_the_caption_zone():
    for t in T.TEMPLATES.values():
        assert not A.check_caption_exclusion("s", t, None), t.name


# ------------------------------------------------------------------ report

def test_a_clean_video_reports_only_the_unresolved_contrast_note():
    scenes = [scene("s01"), scene("s02", template="key_phrase")]
    r = A.lint_accessibility(scenes, palette=None)
    assert r.ok
    assert {f.rule for f in r.findings} == {"contrast_unresolved"}


def test_a_clean_video_with_a_palette_is_completely_clean():
    scenes = [scene("s01"), scene("s02", template="key_phrase")]
    r = A.lint_accessibility(scenes, palette=PALETTE)
    assert r.ok and not r.findings


def test_the_report_names_what_it_could_not_evaluate():
    """The whole point of §16.2 being a compliance gate: 'no findings' must not
    be readable as 'compliant' when the check never ran."""
    r = A.lint_accessibility([scene()], palette=None)
    assert set(r.unresolved) >= {"contrast_ratio", "flash_rate",
                                 "caption_alignment", "audio_description"}
    assert "NOT EVALUATED" in r.render()


def test_a_blocking_finding_makes_the_report_not_ok():
    r = A.lint_accessibility([scene(narration="")], palette=PALETTE)
    assert not r.ok
    assert "caption_impossible" in {f.rule for f in r.blocking}


def test_an_unknown_template_is_left_to_the_pedagogy_linter():
    r = A.lint_accessibility([scene(template="no_such_template")],
                             palette=PALETTE)
    assert not r.findings

"""The token layer — docs/design/video-design-system.md §3.

These tests police the boundary the design system draws: a value is either a
named token or it is a mistake. They are Python tests over TypeScript source
because the repo's test runner is pytest and the property is textual — no
TypeScript toolchain is needed to assert that a component contains no hex
literal.
"""
from __future__ import annotations

import pathlib
import re

RENDER_SRC = pathlib.Path(__file__).resolve().parents[1] / "render" / "src"
TOKENS = RENDER_SRC / "tokens.ts"

# Files allowed to contain raw values. `tokens.ts` IS the design system; every
# other file must read from it.
TOKEN_FILES = {"tokens.ts"}

_HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")


def components() -> list[pathlib.Path]:
    return sorted(p for p in RENDER_SRC.rglob("*.ts*")
                  if p.name not in TOKEN_FILES)


def strip_comments(src: str) -> str:
    """Comments legitimately quote hex values while explaining them."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


# ------------------------------------------------------ §3: no loose colour

def test_no_component_contains_a_hex_literal():
    """ISSUE-18: four hex literals in Scene.tsx did all the work. A colour
    written outside the token layer is a colour with no meaning attached, and
    it is how 'attention' and 'answer' became the same red."""
    offenders = {}
    for p in components():
        found = _HEX.findall(strip_comments(p.read_text(encoding="utf-8")))
        if found:
            offenders[p.name] = sorted(set(found))
    assert not offenders, (
        f"hex literals outside the token layer: {offenders}. Add a semantic "
        f"role to tokens.ts and reference that instead.")


def test_the_token_layer_defines_every_role_the_spec_names():
    """§3's mapping table. If a role is missing, a component will reach for a
    literal to express something the system has no word for."""
    src = TOKENS.read_text(encoding="utf-8")
    for role in ("surface", "surfaceSubtle", "surfaceSignal", "ink", "inkMuted",
                 "inkSubtle", "structure", "structureSubtle", "signal",
                 "signalStrong", "signalSoft", "signalBorder", "answer",
                 "answerSoft", "warning", "warningSoft", "error", "errorSoft"):
        assert re.search(rf"\b{role}:", src), f"§3 role {role!r} is not defined"


def test_the_four_meanings_are_four_different_colours():
    """§3: 'This directly fixes the problem where attention and answer become
    visually identical.' The roles are only useful if they differ."""
    src = TOKENS.read_text(encoding="utf-8")
    values = {}
    for role in ("signal", "answer", "warning", "error"):
        m = re.search(rf'\b{role}: "(#[0-9A-Fa-f]{{6}})"', src)
        assert m, f"{role} has no value"
        values[role] = m.group(1).upper()
    assert len(set(values.values())) == 4, (
        f"roles must be visually distinct, got {values}")


def test_the_source_values_are_the_design_systems_own():
    """§3: 'Do not create new colors.' Spot-check against the §2 token list."""
    src = TOKENS.read_text(encoding="utf-8")
    for role, value in (("signal", "#148AFF"), ("answer", "#05C170"),
                        ("warning", "#FCA106"), ("error", "#D13845"),
                        ("ink", "#262626"), ("inkMuted", "#595959"),
                        ("structure", "#D9D9D9"), ("surface", "#FFFFFF")):
        assert f'{role}: "{value}"' in src, (
            f"{role} must be the design system's {value}")


# ------------------------------------------------------------ §6: the font

def test_the_font_family_is_referenced_through_the_token_layer():
    """So swapping to the design system's real family is one value change, not
    six template edits."""
    for p in components():
        src = strip_comments(p.read_text(encoding="utf-8"))
        assert "sans-serif" not in src or p.name == "tokens.ts", (
            f"{p.name} names a font stack directly; use tokens.font")


def test_the_font_is_self_hosted_and_not_a_cdn_call():
    """§11.3: 'Network fetches at render time → forbidden.'"""
    src = (RENDER_SRC / "fonts.ts").read_text(encoding="utf-8")
    assert "@fontsource/inter" in src
    for cdn in ("fonts.googleapis.com", "fonts.gstatic.com", "https://"):
        assert cdn not in strip_comments(src), f"{cdn} is a network fetch"


def test_the_font_load_is_pinned_before_any_frame_paints():
    """§11.3 names font-loading races. Without the pin, frame 0 renders in the
    fallback family and the scene stops being reproducible."""
    src = (RENDER_SRC / "fonts.ts").read_text(encoding="utf-8")
    assert "delayRender" in src and "document.fonts.ready" in src
    assert "continueRender" in src


def test_the_font_package_is_in_the_render_closure():
    """A font change must invalidate every cached render, or scenes rendered
    before the change are served in the old family forever."""
    import json
    pkg = json.loads((RENDER_SRC.parent / "package.json").read_text(encoding="utf-8"))
    assert "@fontsource/inter" in pkg["dependencies"]


# ------------------------------------------------------- §6: the 24px floor

def test_no_type_role_falls_below_the_24px_floor():
    """§6: 'Never solve a layout problem by shrinking type below 24 px.'"""
    src = TOKENS.read_text(encoding="utf-8")
    sizes = [int(m) for m in re.findall(r"size: (\d+)", src)]
    assert sizes, "no type sizes found"
    assert min(sizes) >= 24, f"a role is below the floor: {sorted(sizes)}"


def test_every_type_size_sits_inside_the_range_the_spec_gives():
    """§6 gives ranges. Picking inside one is a choice; going outside it is
    inventing a value the spec already decided."""
    src = TOKENS.read_text(encoding="utf-8")

    def size_of(role: str) -> int:
        m = re.search(rf"{role}: \{{ size: (\d+)", src)
        assert m, f"{role} missing"
        return int(m.group(1))

    for role, lo, hi in (("display", 72, 88), ("h1", 56, 64), ("h2", 40, 48),
                         ("h3", 32, 36), ("body", 28, 32), ("bodyStrong", 28, 32),
                         ("caption", 24, 26), ("numeric", 64, 88),
                         ("mono", 26, 30)):
        assert lo <= size_of(role) <= hi, (
            f"§6 puts {role} in {lo}–{hi}, got {size_of(role)}")
    assert size_of("label") == 24, "§6 fixes Label at 24"


# ----------------------------------------------------------- §5: spacing

def test_the_spacing_scale_is_the_one_the_spec_derives():
    """§5: 12 → 16 → 24 → 32 → 48 → 64 → 96 → 128."""
    src = TOKENS.read_text(encoding="utf-8")
    m = re.search(r"SPACING_SCALE = \[([^\]]+)\]", src)
    assert m
    scale = [int(x) for x in re.findall(r"\d+", m.group(1))]
    assert scale == [12, 16, 24, 32, 48, 64, 96, 128]


# ------------------------------------------------------------ §4: canvas

def test_the_canvas_margins_are_the_ones_the_spec_gives():
    src = TOKENS.read_text(encoding="utf-8")
    for field, value in (("marginLeft", 96), ("marginRight", 96),
                         ("marginTop", 72), ("columns", 12), ("gutter", 24)):
        assert f"{field}: {value}" in src, f"§4 sets {field} to {value}"


def test_the_caption_zone_supersedes_the_bottom_margin_and_says_so():
    """§4 gives a 64px bottom; §16.2 reserves the bottom 15% (162px) and
    CHALLENGES makes that irreversible. Content laid to 64px would sit under
    the captions. The deviation is recorded rather than absorbed."""
    src = TOKENS.read_text(encoding="utf-8")
    assert "captionZone: 162" in src
    assert "§16.2 wins" in src, "the deviation must be stated where it is made"


# --------------------------------------------------------- §10/§11: motion

def test_every_motion_verb_the_spec_names_exists():
    src = TOKENS.read_text(encoding="utf-8")
    for verb in ("reveal", "build", "focus", "resolve", "transition"):
        assert re.search(rf"\b{verb}: \{{", src), f"§10 verb {verb!r} missing"


def test_every_duration_sits_inside_the_spec_band():
    src = TOKENS.read_text(encoding="utf-8")

    def ms_of(verb: str) -> int:
        m = re.search(rf"{verb}: \{{ ms: (\d+)", src)
        assert m, f"{verb} missing"
        return int(m.group(1))

    for verb, lo, hi in (("reveal", 300, 500), ("build", 400, 700),
                         ("focus", 250, 450), ("resolve", 400, 700)):
        assert lo <= ms_of(verb) <= hi, (
            f"§10 puts {verb} in {lo}–{hi}ms, got {ms_of(verb)}")


def test_focus_scale_stays_inside_the_one_to_three_percent_the_spec_allows():
    """§10.3: 'optional scale change of only 1–3%'."""
    src = TOKENS.read_text(encoding="utf-8")
    m = re.search(r"focus: \{[^}]*scale: ([\d.]+)", src)
    assert m
    assert 1.0 < float(m.group(1)) <= 1.03


def test_the_easing_has_no_overshoot():
    """§11: no bounce, no elastic overshoot. A cubic-bezier whose control
    points stay in [0,1] cannot overshoot."""
    src = TOKENS.read_text(encoding="utf-8")
    m = re.search(r"EASE[^=]*= \[([^\]]+)\]", src)
    assert m
    pts = [float(x) for x in m.group(1).split(",")]
    assert len(pts) == 4
    assert all(0.0 <= p <= 1.0 for p in pts), f"overshooting easing: {pts}"


# ------------------------------------------- §4/§5: layout uses the scale

_SPACING_PROPS = ("padding", "paddingTop", "paddingBottom", "paddingLeft",
                  "paddingRight", "margin", "marginTop", "marginBottom",
                  "marginLeft", "marginRight", "gap", "rowGap", "columnGap")

# §2 gives radius 10 and small radius 8; they are design-system values, not
# spacing, so they are allowed where a radius is set.
_ALLOWED_RADII = {8, 10}


def test_no_layout_value_falls_outside_the_spacing_scale():
    """§5: 'Avoid random values such as 37, 53, 71.' A layout number that is
    not on the scale is a decision nobody made."""
    from_scale = {12, 16, 24, 32, 48, 64, 96, 128, 0}
    offenders = {}
    for p in components():
        src = strip_comments(p.read_text(encoding="utf-8"))
        for prop in _SPACING_PROPS:
            for raw in re.findall(rf"\b{prop}: (\d+)[,\s]", src):
                if int(raw) not in from_scale:
                    offenders.setdefault(p.name, []).append(f"{prop}: {raw}")
    assert not offenders, (
        f"off-scale layout values: {offenders}. §5's scale is "
        f"12/16/24/32/48/64/96/128.")


def test_border_radii_come_from_the_design_system():
    for p in components():
        src = strip_comments(p.read_text(encoding="utf-8"))
        for raw in re.findall(r"borderRadius: (\d+)", src):
            assert int(raw) in _ALLOWED_RADII, (
                f"{p.name}: radius {raw} is not the system's 8 or 10")


def test_the_scene_shell_no_longer_centres_its_content():
    """ISSUE-17: `justifyContent: center` on a column with one short child
    centres that child and leaves the bottom 30-40% dead. §9 asks for the
    opposite on every template."""
    src = (RENDER_SRC / "Scene.tsx").read_text(encoding="utf-8")
    assert 'justifyContent: "center"' not in strip_comments(src)


def test_the_content_region_is_derived_from_the_canvas_tokens():
    """The learner should recognise the same content boundary across templates
    (§4), which requires one boundary rather than per-template padding."""
    src = strip_comments((RENDER_SRC / "Scene.tsx").read_text(encoding="utf-8"))
    for name in ("contentLeft", "contentTop", "contentWidth", "contentHeight"):
        assert name in src, f"the shell must place using {name}"


def test_the_content_region_clears_the_caption_zone():
    """Arithmetic, not intent: content must end above the captions."""
    src = TOKENS.read_text(encoding="utf-8")
    def val(name):
        return int(re.search(rf"{name}: (\d+)", src).group(1))
    height, top = val("height"), val("marginTop")
    usable = height - top - val("captionZone") - val("marginBottom")
    assert usable > 0
    assert top + usable <= height - val("captionZone"), (
        "content region overlaps §16.2's caption exclusion zone")


# ------------------------------------ §6: the renderer uses roles, not maths

def test_the_renderer_sizes_type_by_role():
    """Sizes were arithmetic (minFontPx x3/x2/x1): three magnitudes with no way
    to say 'this is a label' or 'this is a caption'."""
    src = strip_comments((RENDER_SRC / "Scene.tsx").read_text(encoding="utf-8"))
    assert "minFontPx * 3" not in src and "minFontPx * 2" not in src
    assert "typeScale" in src


def test_the_renderer_never_shrinks_below_the_floor():
    """§6's floor is absolute. `px()` clamps UP to minFontPx; nothing clamps
    down."""
    src = strip_comments((RENDER_SRC / "Scene.tsx").read_text(encoding="utf-8"))
    assert "Math.max(r.size, minFontPx)" in src, (
        "the size helper must clamp up to the floor, never down")
    assert "Math.min(" not in src.split("const px =")[-1][:200]


# --------------------------- the linter's model of the renderer, checked

def test_every_registered_template_has_a_slot_role_mapping():
    """`design.SLOT_ROLES` is a MODEL of Scene.tsx. A template missing from it
    is a template the fit check silently skips."""
    from explainer import design, templates
    missing = set(templates.TEMPLATES) - set(design.SLOT_ROLES)
    assert not missing, f"no type mapping for {sorted(missing)}"


def test_every_mapped_role_exists_in_the_token_file():
    from explainer import design
    roles = set(design.type_scale())
    for template, mapping in design.SLOT_ROLES.items():
        for slot, role in mapping.items():
            assert role in roles, f"{template}.{slot} -> unknown role {role!r}"


def test_the_tokens_are_parsed_not_copied():
    """One source of truth. If the parse ever silently returns defaults, the
    fit check measures a layout the renderer is not producing."""
    from explainer import design
    assert design.type_scale()["display"].size == 80
    assert design.canvas()["marginLeft"] == 96
    assert design.min_font_px() == 24


# ------------------------------------------- §10-§12: the motion grammar

def test_the_motion_module_uses_only_the_five_verbs():
    """§10 opens by rejecting "dozens of unrelated animation presets"."""
    src = strip_comments((RENDER_SRC / "motion.ts").read_text(encoding="utf-8"))
    exported = set(re.findall(r"export const (\w+)", src))
    assert {"reveal", "build", "focusAmount", "resolveAmount"} <= exported


def test_every_cue_kind_maps_to_a_verb():
    """The signal designer's four kinds are all ATTENTION events (§12 level 3),
    so all four are FOCUS — differing in what they change, not in when."""
    src = (RENDER_SRC / "motion.ts").read_text(encoding="utf-8")
    for kind in ("highlight", "pointer", "scale_pulse", "dim"):
        assert re.search(rf"{kind}: \"focus\"", src), f"{kind} has no verb"


def test_the_renderer_does_not_invent_cue_times():
    """R3: the resolver computes a cue's time from its span anchor before
    anything renders. A renderer picking its own would be a second opinion
    about §13 narration synchronisation, and the anchored one is right."""
    src = strip_comments((RENDER_SRC / "motion.ts").read_text(encoding="utf-8"))
    assert "atSeconds" in src, "focus must be driven by the resolved time"
    for invented in ("Math.random", "Date.now", "new Date"):
        assert invented not in src


def test_focus_scale_cannot_exceed_the_spec_ceiling():
    """§10.3 allows "only 1–3%". The PRD's §9.2 permits up to 120%; the design
    system is stricter and sits inside that bound, so the stricter wins."""
    src = (RENDER_SRC / "motion.ts").read_text(encoding="utf-8")
    assert "MAX_FOCUS_SCALE" in src
    assert "Math.min(1," in src, "the focus amount must be clamped"


def test_structural_elements_are_not_animated():
    """§12 level 1: "No animation or extremely subtle entrance" for grids,
    dividers, card borders, baselines."""
    src = strip_comments((RENDER_SRC / "Scene.tsx").read_text(encoding="utf-8"))
    baseline = src[src.find("the lane's own baseline"):][:400]
    assert "enter(" not in baseline and "buildStep(" not in baseline


def test_transition_lives_in_assembly_not_in_the_renderer():
    """§10.5's TRANSITION is between concepts, which here means between scenes.
    §11.4 models that as a first-class node with its own cache key. Doing it in
    both places would put transitions in two."""
    src = strip_comments((RENDER_SRC / "motion.ts").read_text(encoding="utf-8"))
    assert "export const transition" not in src
    from explainer import assembly
    assert hasattr(assembly, "Transition")

"""The accessibility linter (Sequence v0.2 §16.2, WCAG 2.2).

§16.2 splits its own gates by when they can run, and this module keeps that
split visible rather than pretending everything is checkable at storyboard time:

    PER-SCENE (pre-render)  — contrast, caption presence, self-describing
                              narration
    PER-RENDER (post-render, on frames) — flash detection, caption safe area

Deterministic. No model calls, ever. §16.2 assigns "self-describing narration"
to the §9.2 coherence check, which §9.6 puts on the model side, so it stays in
`linter.MODEL_BASED_RULES` and is not approximated here.

## What is implemented, and what is merely implementable

The WCAG algorithms are fully specified, so they are written and tested here as
pure functions: relative luminance, contrast ratio, the large-text boundary, and
the PEAT/Harding flash criterion. What does NOT exist yet is their *input*.

- **Contrast** needs resolved colours. `brand_version` is a bare string today —
  there is no palette anywhere in the system, and §16.2 does not name one.
  `check_contrast` therefore returns an `unresolved` finding when no palette is
  bound. It does not pass, and it does not invent a colour. Phase 5 owns brand.
- **Flash** needs frames. `flash_findings` operates on a luminance series that
  only a renderer can produce — week 5 at the earliest.

Writing the math now is not speculation: both are transcribed from published
criteria, both are tested against the values those criteria state, and neither
can be got wrong quietly later when the input arrives.

## The one derived number in this file

§11.6 requires >=24 px at 1080p. WCAG 1.4.3 sets its large-text boundary at
18 pt. CSS defines 1 pt = 4/3 px, so 18 pt == 24 px exactly: **at the registry's
own minimum font size, every text layer is already WCAG "large text"** and the
threshold that applies is 3:1, not 4.5:1. That is a derivation from two stated
numbers and a defined unit conversion, not an authored choice — but it is the
kind of coincidence worth stating out loud, because a future reader who raises
`MIN_FONT_PX` will not notice they have changed which WCAG threshold applies.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import templates
from .prose import Finding

# ===========================================================================
# SPEC NUMBERS — WCAG 2.2 via Sequence v0.2 §16.2. Transcribed, not chosen.
# ===========================================================================

# §16.2 1.4.3 Contrast (AA): "4.5:1 normal, 3:1 large (>=18 pt / 14 pt bold)".
CONTRAST_NORMAL = 4.5
CONTRAST_LARGE = 3.0
LARGE_PT = 18.0
LARGE_PT_BOLD = 14.0

# §16.2 1.4.11 Non-text Contrast (AA): "3:1 for meaningful graphics — applies to
# diagrams, arrows, chart elements".
CONTRAST_NON_TEXT = 3.0

# §16.2 2.3.1 Three Flashes (A): "fail >3 transitions/s over >25% of frame",
# over a "sliding 1s window".
MAX_FLASH_TRANSITIONS_PER_SECOND = 3
FLASH_AREA_FRACTION = 0.25
FLASH_WINDOW_SECONDS = 1.0

# §16.2: "reserve the bottom 15% as a caption exclusion zone in every layout
# template". Same number as templates.CAPTION_SAFE_BOTTOM, asserted equal below
# so the two cannot drift apart.
CAPTION_EXCLUSION_BOTTOM = 0.15

# CSS defines 1 pt = 4/3 px. Not a choice.
PX_PER_PT = 4.0 / 3.0

assert CAPTION_EXCLUSION_BOTTOM == templates.CAPTION_SAFE_BOTTOM, (
    "§16.2's caption exclusion zone and templates.CAPTION_SAFE_BOTTOM are the "
    "same number and must stay equal")

# Gates §16.2 states that cannot run until a later stage supplies their input.
UNRESOLVED_INPUTS = {
    "contrast_ratio":
        "§16.2 1.4.3/1.4.11: WCAG ratio per text layer against its resolved "
        "background. The math is implemented and tested; there is no palette "
        "in the system to run it against — `brand_version` is a bare string "
        "and v0.2 names no colours. Phase 5 owns brand.",
    "flash_rate":
        "§16.2 2.3.1: PEAT/Harding sliding window. The criterion is "
        "implemented and tested; it needs rendered frames, which do not exist "
        "before week 5.",
    "caption_alignment":
        "§16.2: 'every narrated scene has aligned word timings'. Word timings "
        "come from TTS — week 5. What IS checkable now is that a narrated "
        "scene has narration text at all, which `check_caption_presence` does.",
    "audio_description":
        "§16.2 1.2.5 (AA), 'the expensive one'. v0.2's answer is the "
        "self-describing narration rule, which §16.2 routes to the §9.2 "
        "coherence check — model-based per §9.6, so not here.",
}


class PaletteUnresolved(NotImplementedError):
    """Contrast was demanded on a scene with no colours bound."""


# ------------------------------------------------------- WCAG contrast math

_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")


def parse_colour(value: str) -> tuple[int, int, int]:
    """`#rrggbb` to an 8-bit RGB triple. The only format accepted, because a
    palette that permits named colours needs a name table nobody has authored."""
    m = _HEX.match((value or "").strip())
    if not m:
        raise ValueError(
            f"colour {value!r} is not #rrggbb. Named colours and rgb() are not "
            f"accepted: resolving them needs a table this system does not have.")
    h = m.group(1)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def relative_luminance(colour: str | tuple[int, int, int]) -> float:
    """WCAG 2.2 relative luminance. The constants are the standard's."""
    rgb = parse_colour(colour) if isinstance(colour, str) else colour
    chans = []
    for c in rgb:
        s = c / 255.0
        chans.append(s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4)
    r, g, b = chans
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: str | tuple[int, int, int],
                   b: str | tuple[int, int, int]) -> float:
    """WCAG 2.2: (L_lighter + 0.05) / (L_darker + 0.05). Order-independent."""
    la, lb = relative_luminance(a), relative_luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def is_large_text(pt: float, bold: bool = False) -> bool:
    """§16.2's parenthetical: ">=18 pt / 14 pt bold"."""
    return pt >= (LARGE_PT_BOLD if bold else LARGE_PT)


def required_contrast(pt: float, bold: bool = False) -> float:
    return CONTRAST_LARGE if is_large_text(pt, bold) else CONTRAST_NORMAL


def px_to_pt(px: float) -> float:
    return px / PX_PER_PT


# --------------------------------------------------------- PEAT/Harding

@dataclass(frozen=True)
class FlashWindow:
    """One second of frames that failed §16.2's criterion."""

    start_second: float
    transitions: int
    area_fraction: float


def flash_windows(luminance: list[float], area_fraction: list[float],
                  fps: float,
                  threshold: float = 0.10) -> list[FlashWindow]:
    """§16.2 2.3.1: sliding 1 s window, fail >3 transitions/s over >25% of frame.

    PROVISIONAL(D5) — `threshold` is PEAT's number, not v0.2's. See
    docs/week4-decisions-needed.md.

    `luminance` is mean relative luminance per frame and `area_fraction` is the
    fraction of the frame that changed in that frame — both of which only a
    renderer can produce. `threshold` is the luminance delta that counts as a
    transition; PEAT's own general-flash definition is a relative luminance
    change of 0.10 where the darker state is below 0.80, which is what is used
    here rather than an invented number.

    Returns every failing window, not just the first: a report that names one
    flash in a video with nine tells a human to fix it nine times.
    """
    if fps <= 0:
        raise ValueError("fps must be positive")
    if len(luminance) != len(area_fraction):
        raise ValueError(
            f"luminance has {len(luminance)} frames and area_fraction has "
            f"{len(area_fraction)}; they describe the same frames")

    # A transition is a frame-to-frame luminance change of >= threshold whose
    # darker state is below 0.80, per PEAT's general flash definition, AND that
    # covers more than the criterion's area fraction.
    transitions: list[int] = []
    for i in range(1, len(luminance)):
        delta = abs(luminance[i] - luminance[i - 1])
        darker = min(luminance[i], luminance[i - 1])
        if (delta >= threshold and darker < 0.80
                and area_fraction[i] > FLASH_AREA_FRACTION):
            transitions.append(i)

    if not transitions:
        return []

    window = max(1, int(round(fps * FLASH_WINDOW_SECONDS)))
    out: list[FlashWindow] = []
    for start in range(0, len(luminance)):
        end = start + window
        inside = [i for i in transitions if start <= i < end]
        if len(inside) > MAX_FLASH_TRANSITIONS_PER_SECOND:
            out.append(FlashWindow(
                start_second=round(start / fps, 3),
                transitions=len(inside),
                area_fraction=round(max(area_fraction[i] for i in inside), 4)))
    return _merge_overlapping(out, window / fps)


def _merge_overlapping(windows: list[FlashWindow], span: float
                       ) -> list[FlashWindow]:
    """A 4-transition burst fails every window that contains it. A human wants
    one finding per burst, so overlapping windows collapse to their worst."""
    out: list[FlashWindow] = []
    for w in windows:
        if out and w.start_second - out[-1].start_second < span:
            prev = out[-1]
            if w.transitions > prev.transitions:
                out[-1] = FlashWindow(prev.start_second, w.transitions,
                                      max(prev.area_fraction, w.area_fraction))
            continue
        out.append(w)
    return out


def flash_findings(scene_ref: str, luminance: list[float],
                   area_fraction: list[float], fps: float) -> list[Finding]:
    """§16.2 2.3.1 is level A and automated-check-required, so it is blocking."""
    out = []
    for w in flash_windows(luminance, area_fraction, fps):
        out.append(Finding(
            rule="flash_rate", severity="blocking", subject=scene_ref,
            message=f"{w.transitions} luminance transitions in the second at "
                    f"{w.start_second}s over {w.area_fraction:.0%} of frame; "
                    f"§16.2 fails above "
                    f"{MAX_FLASH_TRANSITIONS_PER_SECOND}/s over "
                    f"{FLASH_AREA_FRACTION:.0%}",
            measured={"transitions_per_second": w.transitions,
                      "area_fraction": w.area_fraction,
                      "at_second": w.start_second},
            threshold={"max_transitions_per_second":
                       MAX_FLASH_TRANSITIONS_PER_SECOND,
                       "area_fraction": FLASH_AREA_FRACTION},
            fix="slow the transition or reduce the area that changes; WCAG "
                "2.3.1 is level A and this is a seizure risk, not a polish "
                "note"))
    return out


# ------------------------------------------------------------ scene rules

def check_contrast(scene_ref: str, layers: list[dict] | None,
                   palette: dict | None) -> list[Finding]:
    """§16.2 1.4.3 / 1.4.11.

    PROVISIONAL(D6) — reporting `unresolved` at info rather than staying
    silent. See docs/week4-decisions-needed.md.

    `layers` is [{name, colour, background, pt, bold, non_text}]. When no
    palette is bound this reports `contrast_unresolved` — an INFO finding that
    keeps the gate visible. It deliberately does not pass: §16.2 lists contrast
    as a required pre-render gate, and a silent absence would read as compliance
    in a report §4.3 shows a customer.
    """
    if not palette:
        return [Finding(
            rule="contrast_unresolved", severity="info", subject=scene_ref,
            message="contrast not evaluated: no palette is bound to this "
                    "video. §16.2 requires 4.5:1 (3:1 large, 3:1 non-text) and "
                    "the check cannot run until brand resolves colours",
            measured={"palette": None},
            threshold={"normal": CONTRAST_NORMAL, "large": CONTRAST_LARGE,
                       "non_text": CONTRAST_NON_TEXT},
            fix="Phase 5 binds a brand palette; this becomes a real check then")]

    out: list[Finding] = []
    for layer in layers or []:
        fg = palette.get(layer["colour"], layer["colour"])
        bg = palette.get(layer["background"], layer["background"])
        ratio = contrast_ratio(fg, bg)
        if layer.get("non_text"):
            need, kind = CONTRAST_NON_TEXT, "non-text"
        else:
            need = required_contrast(layer.get("pt", px_to_pt(
                templates.MIN_FONT_PX)), bool(layer.get("bold")))
            kind = "large text" if need == CONTRAST_LARGE else "normal text"
        if ratio < need:
            out.append(Finding(
                rule="contrast_ratio", severity="blocking", subject=scene_ref,
                message=f"{layer.get('name', 'layer')}: {ratio:.2f}:1 against "
                        f"its background, under §16.2's {need}:1 for {kind}",
                measured={"ratio": round(ratio, 3), "foreground": fg,
                          "background": bg, "kind": kind},
                threshold={"min_ratio": need},
                fix="darken the background or lighten the text; WCAG 1.4.3 is "
                    "AA and this one is measurable, so there is no judgement "
                    "call to make"))
    return out


def check_font_size(scene_ref: str, template: templates.Template,
                    overrides: dict | None = None) -> list[Finding]:
    """§11.6: >=24 px at 1080p. The registry already refuses to hold a template
    under the minimum (`templates.check_registry`), so this catches the other
    way in — a scene overriding the size downward."""
    out: list[Finding] = []
    px = (overrides or {}).get("font_px", template.min_font_px)
    if px < templates.MIN_FONT_PX:
        out.append(Finding(
            rule="font_too_small", severity="blocking", subject=scene_ref,
            message=f"{px}px text; §11.6 requires >={templates.MIN_FONT_PX}px "
                    f"at 1080p ({px_to_pt(px):.0f}pt vs "
                    f"{px_to_pt(templates.MIN_FONT_PX):.0f}pt)",
            measured={"font_px": px, "font_pt": round(px_to_pt(px), 1)},
            threshold={"min_font_px": templates.MIN_FONT_PX},
            fix="cut words rather than shrink type; §9.4 caps on-screen text "
                "at 20% of narration for the same reason"))
    return out


def check_caption_exclusion(scene_ref: str, template: templates.Template,
                            spec: dict | None = None) -> list[Finding]:
    """§16.2: "reserve the bottom 15% as a caption exclusion zone in every
    layout template". Two ways this breaks: the template reserves too little,
    or a scene overrides the reservation downward."""
    out: list[Finding] = []
    declared = ((spec or {}).get("captionSafeArea") or {}).get(
        "bottom", template.safe_area.bottom)
    if declared < CAPTION_EXCLUSION_BOTTOM:
        out.append(Finding(
            rule="caption_exclusion_zone", severity="blocking",
            subject=scene_ref,
            message=f"bottom {declared:.0%} reserved; §16.2 requires "
                    f"{CAPTION_EXCLUSION_BOTTOM:.0%} so soft captions cannot "
                    f"occlude content",
            measured={"reserved_bottom": declared},
            threshold={"min_reserved_bottom": CAPTION_EXCLUSION_BOTTOM},
            fix="§16.2 calls reserving this from day one 'the cheap fix that "
                "avoids a painful retrofit across every template you'll ever "
                "ship'"))
    return out


def check_caption_presence(scene_ref: str, narration_text: str) -> list[Finding]:
    """§16.2 1.2.2 Captions (A), "non-negotiable".

    Word timings are week 5, but a scene that carries no narration can never
    have captions, and that is checkable now.
    """
    if (narration_text or "").strip():
        return []
    return [Finding(
        rule="caption_impossible", severity="blocking", subject=scene_ref,
        message="scene has no narration, so no caption track can be produced "
                "for it; §16.2 makes 1.2.2 non-negotiable",
        measured={"narration_chars": 0},
        threshold={"min_narration_chars": 1},
        fix="either narrate the scene or mark it a silent segment, which "
            "§16.2 1.2.1 then requires a descriptive transcript for")]


def check_silent_screen_capture(scene_ref: str, template: templates.Template,
                                narration_text: str) -> list[Finding]:
    """§16.2 1.2.1 (A): "Descriptive transcript for silent screen-capture
    segments". A SCREEN_DEMO scene with no narration is exactly that case."""
    if template.kind is not templates.Kind.SCREEN_DEMO:
        return []
    if (narration_text or "").strip():
        return []
    return [Finding(
        rule="silent_screen_capture", severity="blocking", subject=scene_ref,
        message=f"silent screen capture on '{template.name}'; §16.2 1.2.1 "
                f"requires a descriptive transcript for it",
        measured={"kind": template.kind.value, "narration_chars": 0},
        threshold={"requires": "descriptive transcript"},
        fix="narrate the demo — which also satisfies 1.2.5 through v0.2's "
            "self-describing narration rule, at no extra cost")]


# ------------------------------------------------------------------ report

@dataclass
class A11yReport:
    findings: list[Finding]
    scene_count: int
    unresolved: dict

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.blocking]

    @property
    def ok(self) -> bool:
        return not self.blocking

    def render(self) -> str:
        lines = []
        for sev in ("blocking", "warning", "info"):
            group = [f for f in self.findings if f.severity == sev]
            if not group:
                continue
            lines.append(f"{sev.upper()} ({len(group)})")
            for f in group:
                lines.append(f"  [{f.subject}] {f.rule}: {f.message}")
                if f.fix:
                    lines.append(f"        fix: {f.fix}")
        if not self.findings:
            lines.append("no accessibility findings")
        lines.append("")
        lines.append("NOT EVALUATED (so 'no finding' here is not 'passes'):")
        for rule, why in sorted(self.unresolved.items()):
            lines.append(f"  {rule}: {' '.join(why.split())}")
        return "\n".join(lines)


def lint_accessibility(scenes, palette: dict | None = None) -> A11yReport:
    """Every §16.2 gate whose input exists at storyboard time.

    `scenes` are `linter.SceneView`s, so this runs over the same rows the
    pedagogy linter does and does not need its own loader.
    """
    findings: list[Finding] = []
    if not palette:
        # One note per video, not per scene: "no palette is bound" is a fact
        # about the video, and repeating it nine times buries the findings a
        # human can actually act on.
        findings += check_contrast("video", [], None)
    for s in scenes:
        try:
            t = templates.get(s.template_name)
        except KeyError:
            # The pedagogy linter already reports unknown templates; reporting
            # it twice in two reports helps nobody.
            continue
        findings += check_caption_presence(s.ref, s.narration_text)
        findings += check_silent_screen_capture(s.ref, t, s.narration_text)
        findings += check_font_size(s.ref, t, s.visual_spec)
        findings += check_caption_exclusion(s.ref, t, s.visual_spec)
        if palette:
            findings += check_contrast(
                s.ref, (s.visual_spec or {}).get("layers"), palette)
    return A11yReport(findings=findings, scene_count=len(scenes),
                      unresolved=dict(UNRESOLVED_INPUTS))

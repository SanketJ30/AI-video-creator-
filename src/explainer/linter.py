"""The pedagogy linter (Sequence v0.2 §9.6, enforcing §9.2, §9.3, §9.4).

    §9.6: "Runs at storyboard time, before any expensive generation."
    §4.3: the report is a customer-visible artifact.

Deterministic. No model calls, ever. §9.6 splits the rules itself, and this
module implements exactly one side of that split:

    Deterministic (code, fast, free) — text density, word counts, element
    counts, cue count per scene, video duration, term-registry violations,
    readability, passive-voice ratio, caption safe area.

    Model-based (agentic, slower) — relevance scoring, semantic-similarity
    band for on-screen text, analogy quality, hook strength.

The model-based half is NOT implemented here and NOT approximated. §9.2's
coherence rule (`relevanceScore` below 0.85 blocks) is the most tempting to fake
with string matching, and faking it would produce a number that looks like the
spec's and means something else. `MODEL_BASED_RULES` names what is deliberately
absent so a reader can tell "not implemented" from "passes".

## Rules that need a number the spec does not give

Three §9.4 branches depend on thresholds v0.2 states in words only —
`audience.nonNativeRatio > threshold`, `content.termDensity is high` — and
§9.4's semantic-similarity band needs a model. Those raise
`UnspecifiedThreshold` rather than getting an invented number, the same
discipline the Gagné caps got in week 3. The one authored number in this file is
the template-variety share, which is marked and tabled below because v0.2 has no
variety budget at all (ISSUE-4).

## Severity

§9.6's model, applied literally. Blocking means "will not render": a scene whose
on-screen text reproduces a narration sentence verbatim is blocking, because
§9.4's evidence is that identical text is *worse than no text at all* (.25 vs
.33 recall). Warnings render and are reported. Nothing here is advisory yet.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from . import db, templates
from .prose import Finding, sentences, words

# ===========================================================================
# SPEC NUMBERS — Sequence v0.2. Transcribed, not chosen. Changing one of these
# means the code and the PRD have diverged.
# ===========================================================================

# §9.4 engine rule: "on_screen_text = ABRIDGED key phrases, <=20% of narration
# word count". §8 restates it: "Abridged near-paraphrase, <=20% of narration
# word count".
ONSCREEN_TEXT_MAX_SHARE = 0.20

# §9.3 cognitive load thresholds.
MAX_ONSCREEN_OBJECTS = 7                 # "Simultaneous on-screen objects <=7"
MAX_ONSCREEN_OBJECTS_WITH_TEXT = 4       # "<=4 if any carry text"
MAX_ONSCREEN_WORDS = 30                  # "<=25-30 words visible at once"
# "<=6 words per line for emphasis". Transcribed but NOT enforced — see
# DEFERRED_RULES["words_per_line"]. Kept here so the number stays next to its
# siblings rather than being reconstructed from the spec when layout arrives.
MAX_WORDS_PER_LINE = 6
MAX_TEXT_ELEMENTS = 3                    # "<=3 simultaneous text elements"
MAX_NEW_INTERACTING_ELEMENTS = 4         # "New interacting elements per scene <=4"

# §9.2 Pre-training: ">=3 new technical terms" requires a preceding vocabulary
# scene.
PRETRAINING_NEW_TERM_TRIGGER = 3

# §9.2 Segmenting: "Video length hard cap 6:00, target 3-5. Explicit segment
# boundary every 60-120 s."
VIDEO_HARD_CAP_SECONDS = 360
VIDEO_TARGET_MIN_SECONDS = 180
VIDEO_TARGET_MAX_SECONDS = 300
SEGMENT_BOUNDARY_MAX_SECONDS = 120

# §9.2 Multimedia: "No scene may be narration over a blank or static title for
# >8 s."
STATIC_TITLE_MAX_SECONDS = 8

# §9.2 Signalling — already enforced at design time; re-checked here because
# §9.6 lists "cue count per scene" as a deterministic linter rule and a human
# may have edited a spec since.
MIN_CUES, MAX_CUES = 1, 3

# ===========================================================================
# AUTHORED AND UNREVIEWED — not from Sequence v0.2. One number.
#
# v0.2 has no transition grammar and no variety budget; PRD_v4 §13.5 had both
# and was superseded (ISSUE-4). Reconstructing §13.5's "no more than 2
# consecutive" would make a dead PRD's decision current by the back door, so
# instead this reports the DISTRIBUTION and flags a template that dominates.
# Warning only, never blocking. Argue with the number; do not treat it as spec.
# ===========================================================================

AUTHORED_TEMPLATE_SHARE_MAX = 0.40       # a template carrying >40% of a video

# Rules §9.6 assigns to the model. Named so "absent" is distinguishable from
# "passing" in any report generated from this module.
MODEL_BASED_RULES = {
    "coherence_relevance_score":
        "§9.2 Coherence: relevanceScore = elements with a narration referent / "
        "total elements, fail below 0.85. §9.6 lists relevance scoring as "
        "model-based. A string-matching approximation would produce a number "
        "shaped like the spec's that means something else.",
    "onscreen_semantic_similarity":
        "§9.4: verify 0.3 < semantic_similarity < 0.85 between the on-screen "
        "phrase and the narration — the band between 'identical' and "
        "'far-change'. Needs embeddings; §9.6 lists it as model-based.",
    "analogy_quality": "§9.6, model-based.",
    "hook_strength": "§9.6, model-based.",
    "factual_confidence": "§9.6, model-based.",
}

# Rules that cannot run until a later stage supplies their input.
DEFERRED_RULES = {
    "temporal_contiguity":
        "§9.2: animation starts within ±0.5s of the narration mentioning X, "
        "'enforced automatically from word-level alignment'. Word timings come "
        "from TTS — week 5.",
    "settling_beat":
        "§9.3: >=1.5s of silence with the visual held after each new concept. "
        "Needs resolved timing — week 5.",
    "spatial_contiguity":
        "§9.2: a label sits within <=5% of frame width of its referent. Needs "
        "layout geometry, which exists only after render.",
    "words_per_line":
        "§9.3: '<=6 words per line for emphasis' (MAX_WORDS_PER_LINE). A slot "
        "string does not know where it wraps, and no template declares which "
        "of its slots render as a single line, so there is no line to count "
        "words on until layout exists. The number is transcribed; the rule is "
        "not enforced, and this entry is why that is visible rather than a "
        "constant nobody reads.",
    "contrast_ratio":
        "§16.2 / §9.6: WCAG ratio per text layer against its resolved "
        "background. Needs the resolved theme — accessibility linter, step 5.",
    "flash_rate":
        "§16.2: PEAT/Harding sliding window. Post-render, on frames.",
}


class UnspecifiedThreshold(NotImplementedError):
    """A rule v0.2 states in words without a number."""


# --------------------------------------------------------- scene view

@dataclass
class SceneView:
    """What the linter needs about one scene. Built from stored rows so the
    linter can run over the database without re-planning anything."""

    ref: str
    gagne_slot: str
    narration_text: str
    visual_spec: dict
    pedagogy_meta: dict = field(default_factory=dict)

    @property
    def template_name(self) -> str:
        return (self.visual_spec or {}).get("template", "")

    @property
    def slots(self) -> dict:
        return (self.visual_spec or {}).get("slots", {}) or {}

    @property
    def cues(self) -> list:
        return (self.visual_spec or {}).get("cues", []) or []

    @property
    def seconds(self) -> int:
        return int(self.pedagogy_meta.get("duration_target_seconds") or 0)

    @property
    def new_terms(self) -> list[str]:
        return list(self.pedagogy_meta.get("new_terms") or [])

    @property
    def narration_words(self) -> int:
        return len(words(self.narration_text))


def scene_views(rows: list[dict]) -> list[SceneView]:
    """Build views from `scenes` rows as the CLI loads them."""
    out = []
    for r in rows:
        narration = r.get("narration") or []
        text = r.get("text") or " ".join(s.get("text", "") for s in narration)
        out.append(SceneView(
            ref=r["ref"], gagne_slot=r.get("gagne_slot") or "",
            narration_text=text, visual_spec=r.get("visual_spec") or {},
            pedagogy_meta=r.get("pedagogy_meta") or {}))
    return out


# ------------------------------------------------- on-screen text harvest

# Slot and sub-key names whose value a viewer actually READS. Everything else
# in a filled template is an addressing handle: `focus` and `highlight` name an
# element the cue points at, `chart` is an enum, `icon`/`asset`/`surface` are
# content hashes, `highlight_row` is an index. Counting those as on-screen words
# inflates every §9.4 and §9.3 text measurement — which it did, until a fixture
# measured 6 where 5 was expected and the extra word turned out to be a node id.
_TEXT_KEYS = ("label", "text", "title", "subtitle", "caption", "phrase",
              "term", "characteristic", "detail", "premise", "subject",
              "emphasis", "invariant")


def on_screen_strings(slots: dict, template_name: str = "") -> list[str]:
    """Every string a viewer would read, walked out of the filled slots.

    Two things are excluded, and both were found by measuring rather than by
    reading the code:

    * **Addressing handles.** A node's `id`, `focus`, `chart`, `highlight_row`
      are how a cue names a thing, not something on screen. Harvesting them
      inflated every §9.3 and §9.4 measurement.
    * **Briefs for the imagery.** `cold_open.premise` and
      `concept_illustration.subject` describe what the shot DEPICTS; nothing is
      typeset from them. The template declares this (`Param.on_screen`), and it
      is consulted whenever the template is known — which is why `template_name`
      is worth threading through. Without it, §9.4's priority rule fired on two
      scenes of the real MVCC video that display no text at all.
    """
    skip: set[str] = set()
    if template_name:
        try:
            skip = {p.name for p in templates.get(template_name).params
                    if not p.on_screen}
        except KeyError:
            # An unknown template is reported by check_multimedia; measuring it
            # with the default key set is better than measuring nothing.
            skip = set()

    out: list[str] = []

    def walk(value):
        if isinstance(value, str):
            if value.strip():
                out.append(value.strip())
        elif isinstance(value, list):
            for v in value:
                walk(v)
        elif isinstance(value, dict):
            for k, v in value.items():
                if k in _TEXT_KEYS:
                    walk(v)

    for name, value in slots.items():
        if name in skip:
            continue
        if isinstance(value, str):
            # A top-level scalar counts only if the PARAMETER is text-bearing.
            if name in _TEXT_KEYS:
                walk(value)
        else:
            walk(value)
    return out


def on_screen_word_count(slots: dict, template_name: str = "") -> int:
    return sum(len(words(s)) for s in on_screen_strings(slots, template_name))


def text_element_count(slots: dict, template_name: str = "") -> int:
    """§9.3's "simultaneous text elements" — one per readable string.

    spec question (ISSUE-6), not a settled reading.

    A build template's rows arrive one at a time but they do not leave: at the
    end of a `table_build` all its cells are on screen together, which is what
    "simultaneous" measures. So a 2x2 table is 4 elements and exceeds §9.3's 3.

    That is a real conflict between §9.3 and the template registry rather than a
    counting bug, and it is reported as ISSUE-6 rather than tuned away. Counting
    filled SLOTS instead (a table = 1 element) was tried and rejected: it drops
    the maximum across all 11 registered templates to 2, which makes the rule
    unfireable and therefore worthless.
    """
    return len(on_screen_strings(slots, template_name))


def count_objects(slots: dict) -> tuple[int, bool]:
    """(number of on-screen objects, whether any carries text).

    A list parameter contributes one object per item; a scalar text parameter
    contributes one. This is what §9.3's "simultaneous on-screen objects" counts.
    """
    n = 0
    any_text = False
    for value in slots.values():
        if isinstance(value, list):
            n += len(value)
            if any(isinstance(v, str) or (isinstance(v, dict) and
                                          any(k in _TEXT_KEYS for k in v))
                   for v in value):
                any_text = True
        elif isinstance(value, str) and value.strip():
            n += 1
            any_text = True
        elif value not in (None, "", {}):
            n += 1
    return n, any_text


# ==================================================================== rules
#
# Each returns a list of Findings. `measured` and `threshold` are always
# populated: §4.3 makes the report customer-visible, so a finding without its
# numbers is a broken row.

def check_onscreen_text_share(s: SceneView) -> list[Finding]:
    """§9.4's engine rule, the one the PRD calls the most differentiated
    decision in the product: on-screen text is abridged to <=20% of the
    narration word count when the visual channel is occupied."""
    if not s.slots or not s.narration_words:
        return []
    shown = on_screen_word_count(s.slots, s.template_name)
    allowed = int(s.narration_words * ONSCREEN_TEXT_MAX_SHARE)
    if shown <= allowed:
        return []
    share = shown / s.narration_words
    return [Finding(
        rule="onscreen_text_share", severity="warning", subject=s.ref,
        message=f"{shown} on-screen words against {s.narration_words} narrated "
                f"({share:.0%}); §9.4 abridges to "
                f"{ONSCREEN_TEXT_MAX_SHARE:.0%} ({allowed} words).",
        measured={"onscreen_words": shown, "narration_words": s.narration_words,
                  "share": round(share, 4)},
        threshold={"max_share": ONSCREEN_TEXT_MAX_SHARE, "max_words": allowed},
        fix="cut to key phrases; the evidence favours a near-paraphrase over an "
            "extract")]


def check_verbatim_onscreen(s: SceneView) -> list[Finding]:
    """§9.4: "NEVER render a full narration sentence."

    Blocking, and the severity is the finding's whole point. Yue, Bjork & Bjork
    put identical full text + narration at .25 recall against .33 for no text at
    all — reproducing a sentence on screen is measurably worse than showing
    nothing. It renders fine, which is why nothing else would catch it.
    """
    out: list[Finding] = []
    narration_sentences = {_norm(x) for x in sentences(s.narration_text)}
    if not narration_sentences:
        return out
    for shown in on_screen_strings(s.slots, s.template_name):
        n = _norm(shown)
        if not n:
            continue
        if n in narration_sentences:
            out.append(Finding(
                rule="verbatim_narration_onscreen", severity="blocking",
                subject=s.ref,
                message=f'on-screen text reproduces a narration sentence '
                        f'verbatim: "{shown[:90]}"',
                measured={"onscreen_text": shown[:200]},
                threshold={"rule": "§9.4 never render a full narration sentence"},
                fix="replace with a key phrase or a near-paraphrase — identical "
                    "text scores below showing no text at all (.25 vs .33)"))
    return out


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


def check_object_count(s: SceneView) -> list[Finding]:
    """§9.3: <=7 simultaneous on-screen objects, <=4 if any carry text."""
    n, has_text = count_objects(s.slots)
    limit = MAX_ONSCREEN_OBJECTS_WITH_TEXT if has_text else MAX_ONSCREEN_OBJECTS
    if n <= limit:
        return []
    return [Finding(
        rule="onscreen_object_count", severity="warning", subject=s.ref,
        message=f"{n} on-screen objects against §9.3's limit of {limit}"
                + (" (objects carry text)" if has_text else ""),
        measured={"objects": n, "objects_carry_text": has_text},
        threshold={"max_objects": limit,
                   "max_without_text": MAX_ONSCREEN_OBJECTS,
                   "max_with_text": MAX_ONSCREEN_OBJECTS_WITH_TEXT},
        fix="split across two scenes, or drop the items the narration never names")]


def check_text_density(s: SceneView) -> list[Finding]:
    """§9.3: <=25-30 words visible at once, <=3 simultaneous text elements,
    <=6 words per line for emphasis."""
    out: list[Finding] = []
    strings = on_screen_strings(s.slots, s.template_name)
    total = sum(len(words(x)) for x in strings)
    if total > MAX_ONSCREEN_WORDS:
        out.append(Finding(
            rule="onscreen_text_density", severity="warning", subject=s.ref,
            message=f"{total} words visible at once, over §9.3's "
                    f"{MAX_ONSCREEN_WORDS}",
            measured={"onscreen_words": total},
            threshold={"max_words": MAX_ONSCREEN_WORDS},
            fix="the narration carries the explanation; the screen carries the "
                "key phrase"))
    elements = text_element_count(s.slots, s.template_name)
    if elements > MAX_TEXT_ELEMENTS:
        out.append(Finding(
            rule="onscreen_text_elements", severity="warning", subject=s.ref,
            message=f"{elements} simultaneous text elements, over §9.3's "
                    f"{MAX_TEXT_ELEMENTS}",
            measured={"text_elements": elements},
            threshold={"max_elements": MAX_TEXT_ELEMENTS},
            fix="merge or drop; three is what a viewer can hold while listening"))
    return out


def check_pretraining(s: SceneView, has_preceding_vocab: bool) -> list[Finding]:
    """§9.2 Pre-training: a scene introducing >=3 new technical terms must be
    preceded by a vocabulary scene."""
    n = len(s.new_terms)
    if n < PRETRAINING_NEW_TERM_TRIGGER or has_preceding_vocab:
        return []
    return [Finding(
        rule="pretraining_missing", severity="warning", subject=s.ref,
        message=f"introduces {n} new terms ({', '.join(s.new_terms)}) with no "
                f"preceding vocabulary scene. §9.2 requires one at "
                f"{PRETRAINING_NEW_TERM_TRIGGER}.",
        measured={"new_terms": n, "terms": s.new_terms},
        threshold={"trigger": PRETRAINING_NEW_TERM_TRIGGER},
        fix="add a term_card scene before this one, or move a term to an "
            "earlier scene")]


def check_new_interacting_elements(s: SceneView) -> list[Finding]:
    """§9.3: <=4 new interacting elements per scene, else "the planner must
    decompose into an isolated-elements → interacting-elements sequence".

    Approximated by new terms plus edges, which is what the scene graph knows.
    The approximation is named in the finding so nobody reads it as the spec's
    own measure.
    """
    edges = s.slots.get("edges")
    n = len(s.new_terms) + (len(edges) if isinstance(edges, list) else 0)
    if n <= MAX_NEW_INTERACTING_ELEMENTS:
        return []
    return [Finding(
        rule="interacting_elements", severity="warning", subject=s.ref,
        message=f"about {n} new interacting elements (new terms + relations) "
                f"against §9.3's {MAX_NEW_INTERACTING_ELEMENTS}. Approximated "
                f"from the scene graph — see the rule docstring.",
        measured={"new_terms": len(s.new_terms),
                  "relations": len(edges) if isinstance(edges, list) else 0,
                  "approximation": "new_terms + edges"},
        threshold={"max": MAX_NEW_INTERACTING_ELEMENTS},
        fix="§9.3: decompose into isolated elements, then their interaction")]


def check_cue_count(s: SceneView) -> list[Finding]:
    """§9.2 Signalling, re-checked at lint time — §9.6 lists cue count per
    scene as a deterministic rule, and a human may have edited a spec."""
    if not s.template_name:
        return []
    try:
        template = templates.get(s.template_name)
    except templates.TemplateError:
        return [Finding(
            rule="unknown_template", severity="blocking", subject=s.ref,
            message=f"visual_spec names template '{s.template_name}', which is "
                    f"not in the registry",
            measured={"template": s.template_name},
            threshold={"known": sorted(templates.TEMPLATES)},
            fix="re-run the visual planner")]
    n = len(s.cues)
    if not template.supports_signalling:
        return []          # ISSUE-5
    if MIN_CUES <= n <= MAX_CUES:
        return []
    return [Finding(
        rule="signalling_count", severity="warning", subject=s.ref,
        message=f"{n} signalling events; §9.2 requires {MIN_CUES}-{MAX_CUES} "
                f"per scene, never zero",
        measured={"cues": n, "template": template.name},
        threshold={"min": MIN_CUES, "max": MAX_CUES},
        fix="re-run the signal designer for this scene")]


def check_multimedia(s: SceneView) -> list[Finding]:
    """§9.2 Multimedia: "No scene may be narration over a blank or static title
    for >8 s. Every scene has a visual spec." """
    out: list[Finding] = []
    if not s.visual_spec or not s.template_name:
        out.append(Finding(
            rule="missing_visual_spec", severity="blocking", subject=s.ref,
            message="no visual spec. §9.2: every scene has one.",
            measured={"has_spec": False}, threshold={"required": True},
            fix="run `explainer storyboard plan`"))
        return out
    if s.template_name == "title_card" and s.seconds > STATIC_TITLE_MAX_SECONDS:
        out.append(Finding(
            rule="static_title_too_long", severity="warning", subject=s.ref,
            message=f"a static title held for {s.seconds}s; §9.2 caps narration "
                    f"over a static title at {STATIC_TITLE_MAX_SECONDS}s",
            measured={"seconds": s.seconds, "template": s.template_name},
            threshold={"max_seconds": STATIC_TITLE_MAX_SECONDS},
            fix="give the scene a visual, or shorten it"))
    return out


def check_caption_safe_area(s: SceneView) -> list[Finding]:
    """§16.2 / §9.6. The spec is the template's; this catches a stored spec
    whose safe area was edited away or predates the registry."""
    if not s.template_name:
        return []
    try:
        template = templates.get(s.template_name)
    except templates.TemplateError:
        return []
    got = (s.visual_spec or {}).get("captionSafeArea") or {}
    bottom = got.get("bottom")
    if bottom is not None and bottom >= template.safe_area.bottom:
        return []
    return [Finding(
        rule="caption_safe_area", severity="blocking", subject=s.ref,
        message=f"caption safe area reserves {bottom!r} of the frame bottom; "
                f"§16.2 requires {template.safe_area.bottom}",
        measured={"bottom": bottom},
        threshold={"required_bottom": template.safe_area.bottom},
        fix="re-run the visual planner; the safe area comes from the template "
            "and is not the model's to set")]


# ------------------------------------------------------------ video rules

def check_video_duration(scenes: list[SceneView]) -> list[Finding]:
    """§9.2 Segmenting: hard cap 6:00, target 3-5 minutes."""
    total = sum(s.seconds for s in scenes)
    if not total:
        return []
    out: list[Finding] = []
    if total > VIDEO_HARD_CAP_SECONDS:
        out.append(Finding(
            rule="video_over_hard_cap", severity="blocking", subject="video",
            message=f"{total}s total against §9.2's hard cap of "
                    f"{VIDEO_HARD_CAP_SECONDS}s",
            measured={"seconds": total},
            threshold={"hard_cap": VIDEO_HARD_CAP_SECONDS},
            fix="split the video at an objective boundary"))
    elif not (VIDEO_TARGET_MIN_SECONDS <= total <= VIDEO_TARGET_MAX_SECONDS):
        out.append(Finding(
            rule="video_outside_target_band", severity="warning", subject="video",
            message=f"{total}s total; §9.2 targets "
                    f"{VIDEO_TARGET_MIN_SECONDS}-{VIDEO_TARGET_MAX_SECONDS}s",
            measured={"seconds": total},
            threshold={"target_min": VIDEO_TARGET_MIN_SECONDS,
                       "target_max": VIDEO_TARGET_MAX_SECONDS},
            fix="adjust the brief's target_seconds_per_video"))

    running = 0
    for s in scenes:
        running += s.seconds
        if s.seconds > SEGMENT_BOUNDARY_MAX_SECONDS:
            out.append(Finding(
                rule="segment_too_long", severity="warning", subject=s.ref,
                message=f"{s.seconds}s in one scene; §9.2 wants a segment "
                        f"boundary every {SEGMENT_BOUNDARY_MAX_SECONDS}s at most",
                measured={"seconds": s.seconds},
                threshold={"max_seconds": SEGMENT_BOUNDARY_MAX_SECONDS},
                fix="split the scene at a conceptual unit"))
    return out


def longest_template_run(scenes: list[SceneView]) -> tuple[int, str]:
    """The longest run of CONSECUTIVE identical templates, and which template.

    Reported as a bare number with no threshold attached, deliberately. Share
    and run length measure different failures and neither substitutes for the
    other: 4 of 9 scenes spread across a video is variety, the same 4 back to
    back is monotony, and the share metric cannot tell them apart. On video v2
    the share is 44% (arguably fine) while the run is 3 (s05-s07, all
    `table_build`) — which is the one a viewer would actually notice.

    No number is invented here because v0.2 gives none and old-PRD §13.5's "no
    more than 2 consecutive" is superseded (ISSUE-4). The count is surfaced and
    a human decides.
    """
    best_n, best_name = 0, ""
    run_n, run_name = 0, ""
    for s in scenes:
        if s.template_name and s.template_name == run_name:
            run_n += 1
        else:
            run_name, run_n = s.template_name, 1 if s.template_name else 0
        if run_n > best_n:
            best_n, best_name = run_n, run_name
    return best_n, best_name


def _distribution(scenes: list[SceneView]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for s in scenes:
        if s.template_name:
            counts[s.template_name] = counts.get(s.template_name, 0) + 1
    return counts


def check_template_variety(scenes: list[SceneView]) -> list[Finding]:
    """AUTHORED AND UNREVIEWED — see the table above and ISSUE-4.

    v0.2 has no variety budget. This reports the distribution and flags a
    template that dominates. Warning only. The number is arguable and is printed
    in every finding so it can be argued with.

    The consecutive-run length travels with the finding but never fires one —
    see `longest_template_run`.
    """
    if not scenes:
        return []
    counts: dict[str, int] = {}
    for s in scenes:
        if s.template_name:
            counts[s.template_name] = counts.get(s.template_name, 0) + 1
    if not counts:
        return []
    total = sum(counts.values())
    out: list[Finding] = []
    for name, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        share = n / total
        if share > AUTHORED_TEMPLATE_SHARE_MAX:
            out.append(Finding(
                rule="template_variety", severity="warning", subject="video",
                message=f"template '{name}' carries {n} of {total} scenes "
                        f"({share:.0%}). NOTE: the "
                        f"{AUTHORED_TEMPLATE_SHARE_MAX:.0%} threshold is "
                        f"AUTHORED AND UNREVIEWED — v0.2 has no variety budget "
                        f"(ISSUE-4).",
                measured={"template": name, "scenes": n, "of": total,
                          "share": round(share, 4), "distribution": counts,
                          "longest_consecutive_run": longest_template_run(
                              scenes)[0]},
                threshold={"max_share": AUTHORED_TEMPLATE_SHARE_MAX,
                           "authored": True, "spec_source": None},
                fix="vary the treatment, or restore a variety budget to the PRD"))
    return out


# ------------------------------------------------------- unspecified rules

def check_nonnative_text_allowance(non_native_ratio: float) -> list[Finding]:
    """§9.4: "ELSE IF audience.nonNativeRatio > threshold ... permit fuller
    on-screen text". v0.2 never states the threshold."""
    raise UnspecifiedThreshold(
        "§9.4 branches on `audience.nonNativeRatio > threshold` but Sequence "
        "v0.2 states no threshold. Implementing this means picking the number "
        "that decides when the redundancy rule inverts — that belongs in the "
        "PRD, not here. The brief's native_language_ratio is captured and "
        "stored; only the branch point is missing.")


def check_term_density_allowance(scenes: list[SceneView]) -> list[Finding]:
    """§9.4: "OR content.termDensity is high". v0.2 states no measure and no
    threshold."""
    raise UnspecifiedThreshold(
        "§9.4 branches on `content.termDensity is high` but Sequence v0.2 "
        "defines neither the measure nor the threshold. new_terms per scene is "
        "the obvious candidate and the number is still a decision for the PRD.")


# ==================================================================== report

@dataclass
class LintReport:
    findings: list[Finding]
    scene_count: int = 0
    not_implemented: dict = field(default_factory=dict)
    # Bare measurements with no threshold attached. They are NOT findings: a
    # number nobody has set a limit for cannot pass or fail, and putting it in
    # `findings` would either invent a threshold or make every clean video
    # report something. The CLI prints them so they are seen either way.
    stats: dict = field(default_factory=dict)

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.blocking]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "warning"]

    @property
    def ok(self) -> bool:
        """§6 Stage 3: "Scenes that fail hard checks do not render." """
        return not self.blocking

    def blocking_scenes(self) -> list[str]:
        return sorted({f.subject for f in self.blocking if f.subject != "video"})

    def render(self) -> str:
        lines: list[str] = []
        if self.blocking:
            lines.append(f"BLOCKING ({len(self.blocking)}) — will not render")
            for f in sorted(self.blocking, key=lambda f: (f.subject, f.rule)):
                lines.append(f"  [{f.subject}] {f.rule}: {f.message}")
                if f.fix:
                    lines.append(f"        fix: {f.fix}")
        if self.warnings:
            lines.append(f"WARNING ({len(self.warnings)}) — renders, flagged")
            for f in sorted(self.warnings, key=lambda f: (f.subject, f.rule)):
                lines.append(f"  [{f.subject}] {f.rule}: {f.message}")
                if f.fix:
                    lines.append(f"        fix: {f.fix}")
        if not self.findings:
            lines.append(f"pedagogy linter: all deterministic checks pass "
                         f"({self.scene_count} scenes)")
        if self.not_implemented:
            lines.append("")
            lines.append("NOT CHECKED (so 'no finding' here is not 'passes'):")
            for rule, why in sorted(self.not_implemented.items()):
                lines.append(f"  {rule}: {' '.join(why.split())}")
        return "\n".join(lines)


def scene_findings(s: SceneView, has_preceding_vocab: bool) -> list[Finding]:
    """The rules that measure ONE scene. Split out from the video-level rules
    because the two answer different questions: `video_outside_target_band` and
    `template_variety` are properties of a whole video and fire by construction
    on any single scene, so a caller checking one scene must not get them."""
    return (check_multimedia(s) + check_caption_safe_area(s)
            + check_cue_count(s) + check_onscreen_text_share(s)
            + check_verbatim_onscreen(s) + check_object_count(s)
            + check_text_density(s) + check_new_interacting_elements(s)
            + check_pretraining(s, has_preceding_vocab))


def lint(scenes: list[SceneView]) -> LintReport:
    """Every deterministic rule §9.2/§9.3/§9.4 states, over one video."""
    findings: list[Finding] = []
    vocab_seen = False
    for s in scenes:
        findings += scene_findings(s, vocab_seen)
        if s.template_name == "term_card":
            vocab_seen = True
    findings += check_video_duration(scenes)
    findings += check_template_variety(scenes)
    run_n, run_name = longest_template_run(scenes)
    return LintReport(
        findings=findings, scene_count=len(scenes),
        not_implemented={**MODEL_BASED_RULES, **DEFERRED_RULES},
        stats={"longest_consecutive_template_run": run_n,
               "longest_run_template": run_name,
               "template_distribution": _distribution(scenes),
               "target_seconds_total": sum(s.seconds for s in scenes)})


# ------------------------------------------------------------ persistence

LINT_RULES = ("onscreen_text_share", "verbatim_narration_onscreen",
              "onscreen_object_count", "onscreen_text_density",
              "onscreen_text_elements", "pretraining_missing",
              "interacting_elements", "signalling_count", "unknown_template",
              "missing_visual_spec", "static_title_too_long",
              "caption_safe_area", "video_over_hard_cap",
              "video_outside_target_band", "segment_too_long",
              "template_variety")


def save_findings(conn, video_id: str, report: LintReport,
                  scene_ids: dict[str, str] | None = None) -> int:
    """§4.3: the report is a customer-visible artifact, so it is stored."""
    scene_ids = scene_ids or {}
    db.execute(conn, """delete from linter_findings
                         where video_id = %s and rule = any(%s)""",
               (video_id, list(LINT_RULES)))
    for f in report.findings:
        db.execute(conn, """
            insert into linter_findings(video_id, scene_id, rule, severity,
                                        message, measured, threshold, fix)
            values (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (video_id, scene_ids.get(f.subject), f.rule, f.severity, f.message,
              json.dumps(f.measured), json.dumps(f.threshold),
              json.dumps({"suggestion": f.fix}) if f.fix else None))
    return len(report.findings)

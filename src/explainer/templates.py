"""The typed scene template registry (Sequence v0.2 §4.4, §8, §16.2).

Code and data only. No model calls — the visual planner *chooses* a template and
fills its slots; this module says what the templates are and what a valid filling
looks like.

## What a template is

§4.4 defines the composition: "A Sequence video is a narrated motion-graphics
video", whose default on-screen content is animated diagrams, kinetic typography,
data coming to life, screen demos, and illustrations, with stock used sparingly
for a hook or a real-world referent. Each of those is a `Kind` here, and each
concrete template is one layout within a kind.

A template declares four things a planner and a linter both need:

  * **a parameter schema** — what slots it has and what type each takes, so a
    filled template can be validated without rendering it;
  * **a duration band** — below `min_sec` the treatment cannot land, above
    `max_sec` it outstays its welcome;
  * **whether it supports signalling** — §9.2 requires 1–3 signalling events per
    scene, so a template that cannot host a cue constrains what the signal
    designer may do to a scene using it;
  * **a caption safe area** — non-negotiable, see below.

## Caption safe area, and why it is a property rather than a parameter

§16.2's automated gates: *"caption safe area: reserve the bottom 15% as a caption
exclusion zone in every layout template"*, and immediately after: *"Reserving the
caption safe zone in layout templates from day one is the cheap fix that avoids a
painful retrofit across every template you'll ever ship."* CHALLENGES lists it in
the irreversible-decisions table for the same reason.

So it is a column on the template and a field here, never a parameter a caller
can pass. A caller who could override it would eventually override it, and the
retrofit CHALLENGES warns about would arrive one template at a time.

## Renderer-agnostic (CHALLENGES R8)

Parameter types are primitives, lists and enums. No Remotion constructs, no
component names, no JSX, no CSS. A template says *"a labelled diagram with N
nodes and a highlight target"*, not *"the <DiagramReveal/> component"*. The
`renderer` field on every row is `agnostic`, and the test suite asserts it: a
concrete engine name would be a visible exception rather than a silent coupling,
and R8 is what keeps a second engine from being a rewrite.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum

from . import db

# §16.2. Fractions of the frame reserved from layout in every template.
CAPTION_SAFE_BOTTOM = 0.15
# §11.6: ">=24 px minimum font at 1080p" — aggressive encoding rings small text.
MIN_FONT_PX = 24


class Kind(str, Enum):
    """§4.4's composition types, in the priority order §4.4 states:
    rendered diagram/UI → illustration → stock (hook/real-world)."""

    ANIMATED_DIAGRAM = "animated_diagram"
    KINETIC_TYPE = "kinetic_type"
    DATA_VIZ = "data_viz"
    SCREEN_DEMO = "screen_demo"
    ILLUSTRATION = "illustration"
    TITLE_HOOK = "title_hook"


class ParamType(str, Enum):
    TEXT = "text"
    TEXT_LIST = "text_list"
    NODE_LIST = "node_list"        # [{id, label}] — a diagram's addressable parts
    EDGE_LIST = "edge_list"        # [{from, to, label}]
    ROW_LIST = "row_list"          # [{cells: [str, ...]}] — a table row, per column
    SERIES = "series"              # [{label, value}] — data, renderer-neutral
    STEP_LIST = "step_list"        # [{label, detail}] — ordered procedure steps
    ASSET_REF = "asset_ref"        # a content sha in media_assets (R7)
    ENUM = "enum"
    INT = "int"


@dataclass(frozen=True)
class SafeArea:
    """Fractions of the frame reserved from layout. Not a parameter."""

    bottom: float = CAPTION_SAFE_BOTTOM
    top: float = 0.0
    left: float = 0.0
    right: float = 0.0

    def to_json(self) -> dict:
        return asdict(self)

    @property
    def usable_height(self) -> float:
        return round(1.0 - self.bottom - self.top, 6)


@dataclass(frozen=True)
class Param:
    name: str
    type: ParamType
    required: bool = True
    description: str = ""
    # For ENUM only.
    choices: tuple[str, ...] = ()
    # For list types: the most items the layout can hold legibly. §9.3 caps
    # simultaneous on-screen objects at 7, and 4 if any carry text.
    max_items: int | None = None
    # Whether a viewer READS this value, as opposed to it describing what the
    # shot depicts. `cold_open.premise` and `concept_illustration.subject` are
    # briefs for the imagery — nothing is typeset from them — so counting them
    # as on-screen text made §9.4's priority rule fire on scenes with no visible
    # text at all. Every TEXT param declares this explicitly rather than
    # defaulting, so the same ambiguity cannot recur silently on a new template.
    on_screen: bool = True

    def to_json(self) -> dict:
        out = {"type": self.type.value, "required": self.required,
               "description": self.description}
        if self.choices:
            out["choices"] = list(self.choices)
        if self.max_items is not None:
            out["max_items"] = self.max_items
        return out


@dataclass(frozen=True)
class Template:
    name: str
    version: str
    kind: Kind
    description: str
    params: tuple[Param, ...]
    min_sec: float
    max_sec: float
    # WHY THIS IS A REASON AND NOT A BOOLEAN.
    #
    # It used to be `supports_signalling: bool`, and setting it False silently
    # switched off §9.2 — which states "every scene contains 1-3 signalling
    # events, never zero" with no exceptions — for that template. On v2 that
    # exempted 6 of 9 scenes, so two thirds of the video had no signalling and
    # NOTHING REPORTED IT. The flag was mine; the rule is the spec's.
    #
    # A capability flag that disables a pedagogical rule has to carry its own
    # justification and has to be visible where it takes effect. Empty means the
    # template supports signalling, which is the default. A non-empty string is
    # the stated reason it cannot, and `linter.check_signalling_exemption`
    # surfaces that reason as an info finding on every scene it suppresses a
    # rule for.
    signalling_exemption: str = ""
    safe_area: SafeArea = field(default_factory=SafeArea)
    renderer: str = "agnostic"
    min_font_px: int = MIN_FONT_PX
    # Conditions that must hold before a CAPABILITY of this template may ship.
    # Not a validation rule — nothing here blocks a render. It is a standing
    # note attached to the thing it constrains, so it travels with the template
    # instead of living in a findings doc nobody opens while editing it.
    preconditions: tuple[str, ...] = ()
    # Does this template's motion have a tempo of its own?
    #
    # §15.3's `rigid` exists for a visual that must hold its authored duration
    # because its animation lands on beats the audio cannot move. That is a
    # property of the TEMPLATE, not a judgement the script writer should make
    # per scene — the writer sees narration, not motion.
    #
    # MEASURED: every animation in Scene.tsx is a pure function of
    # `progress = frame / (durationInFrames - 1)`, so every template stretches
    # to whatever duration it is given. NO template in this registry has an
    # intrinsic tempo, and none sets this True. Two v2 scenes were nonetheless
    # marked `rigid` by the model, and s04 consequently held 15.49 s of silence
    # — 17% of its duration against §15.3's 15% budget — to protect a tempo that
    # does not exist.
    #
    # CHECKED AGAINST THE DESIGN SYSTEM §9 and §10 — still False for all.
    #
    # §10 gives every motion verb a duration band in MILLISECONDS (REVEAL
    # 300–500, BUILD 400–700, FOCUS 250–450, RESOLVE 400–700) and those are now
    # implemented as fixed durations rather than fractions of the scene. §9.1
    # goes further and choreographs a cold open's entrance to a 1.2–2.0 s total.
    #
    # Neither earns `rigid`. Both describe how long an ELEMENT takes to arrive,
    # not how long the SCENE must last: a cold open with a 1.5 s entrance is
    # equally correct at 8 s or at 15 s, because the entrance does not scale
    # with the scene. And §13 makes the ordering narration-driven — "the
    # animation should follow the spoken explanation" — which is the opposite of
    # a visual holding its own tempo against the audio.
    #
    # A template earns this when its motion lands on beats the audio cannot
    # move: a music-locked build, or a screen recording replayed at its captured
    # rate. Nothing in §9 describes one. Until then, asking for rigid is asking
    # for silence.
    intrinsic_tempo: bool = False

    def param(self, name: str) -> Param:
        for p in self.params:
            if p.name == name:
                return p
        raise KeyError(
            f"template '{self.name}' has no parameter '{name}'. It has: "
            f"{[p.name for p in self.params]}")

    def param_names(self) -> list[str]:
        return [p.name for p in self.params]

    def param_schema(self) -> dict:
        return {p.name: p.to_json() for p in self.params}

    @property
    def supports_signalling(self) -> bool:
        """§9.2 applies unless this template states why it cannot."""
        return not self.signalling_exemption

    def fits(self, seconds: float) -> bool:
        return self.min_sec <= seconds <= self.max_sec


# ---------------------------------------------------------------- registry
#
# Duration bands are engineering judgement, not spec: §4.4 names the composition
# types and §9.1 budgets the SLOTS, but nothing states how long a given layout
# needs. They are set so that a template's band overlaps the slots it is
# plausibly used in, and they are the first thing to change if a planner keeps
# finding no template fits.

TEMPLATES: dict[str, Template] = {
    t.name: t for t in [
        Template(
            name="labelled_diagram", version="1.1.0", kind=Kind.ANIMATED_DIAGRAM,
            description="Nodes and edges that build up, with one focus target. "
                        "The default for structure, flow and relationships (§4.4).",
            params=(
                Param("title", ParamType.TEXT, required=False,
                      description="short heading; omitted when the narration says it"),
                Param("nodes", ParamType.NODE_LIST, max_items=7,
                      description="§9.3 caps simultaneous on-screen objects at 7"),
                Param("edges", ParamType.EDGE_LIST, required=False, max_items=10),
                Param("focus", ParamType.TEXT, required=False,
                      description="node id the scene builds toward"),
            ),
            min_sec=8, max_sec=120),

        Template(
            name="state_timeline", version="1.2.0", kind=Kind.ANIMATED_DIAGRAM,
            description="Parallel tracks advancing through time — two sessions, "
                        "two threads, a before/after. The one template where the "
                        "referent genuinely changes over time (§8).",
            params=(
                Param("tracks", ParamType.TEXT_LIST, max_items=4,
                      description="one label per lane; 4 is the §9.3 text-bearing cap"),
                # Each step names the track it happens on, so it can be drawn
                # in that lane. Without it the renderer had no way to place a
                # step and drew a flat list under decorative headers — the one
                # thing this template exists to show (two things advancing in
                # parallel) was the thing it did not show.
                Param("steps", ParamType.STEP_LIST, max_items=10,
                      description="ordered events; each needs `track` naming "
                                  "which lane it belongs to, matching an entry "
                                  "in `tracks`"),
                Param("invariant", ParamType.TEXT, required=False,
                      description="a rule shown holding, then breaking"),
            ),
            min_sec=15, max_sec=120),

        Template(
            name="key_phrase", version="1.2.0", kind=Kind.KINETIC_TYPE,
            description="One phrase, typeset large. §9.4's abridged near-paraphrase "
                        "lives here — never a full narration sentence.",
            preconditions=(
                "Word-level kinetic typography must not ship while word "
                "timings are estimated. §16.1 drives per-word highlighting "
                "from the word sidecar; align.py MEASURES span boundaries and "
                "ESTIMATES word boundaries inside them "
                "(WORD_METHOD='estimated:syllable_weighted'), because this "
                "voice exports no alignment outputs. Highlighting a word at an "
                "estimated time looks right on a short line and drifts on a "
                "long one. Precondition: a TTS voice with native word "
                "timestamps, or MFA. Until then this template holds its phrase "
                "and does not animate per word. (W3)",),
            params=(
                Param("phrase", ParamType.TEXT,
                      description="≤20% of the scene's narration word count (§9.4)"),
                Param("emphasis", ParamType.TEXT, required=False,
                      description="the word carrying the stress"),
            ),
            min_sec=3, max_sec=20),

        Template(
            name="term_card", version="1.2.0", kind=Kind.KINETIC_TYPE,
            description="A term, its one-line characteristic, and an icon. §9.2's "
                        "pre-training rule emits this when a scene introduces ≥3 "
                        "new terms.",
            params=(
                Param("term", ParamType.TEXT),
                Param("characteristic", ParamType.TEXT,
                      description="one line, not a dictionary definition"),
                Param("icon", ParamType.ASSET_REF, required=False),
            ),
            min_sec=4, max_sec=15),

        Template(
            name="series_build", version="1.2.0", kind=Kind.DATA_VIZ,
            description="A chart that builds. §4.4's 'data coming to life'.",
            params=(
                Param("title", ParamType.TEXT, required=False),
                Param("chart", ParamType.ENUM,
                      choices=("bar", "line", "area", "scatter"),
                      description="renderer-neutral chart family, not a component"),
                Param("series", ParamType.SERIES, max_items=12),
                Param("highlight", ParamType.TEXT, required=False,
                      description="series label the narration points at"),
            ),
            min_sec=8, max_sec=90),

        Template(
            name="table_build", version="1.2.0", kind=Kind.DATA_VIZ,
            description="Rows revealed in order. Comparison where the cells are "
                        "the content.",
            params=(
                Param("columns", ParamType.TEXT_LIST, max_items=4,
                      description="4 is the §9.3 cap when objects carry text"),
                # ROW_LIST, not TEXT_LIST. As TEXT_LIST the model packed every
                # column into one string separated by '|', the renderer drew it
                # as one full-width line, and the column headers aligned with
                # nothing — a table with no columns. One cell per column, and
                # the count is checked against `columns`.
                Param("rows", ParamType.ROW_LIST, max_items=8,
                      description="one entry per row; `cells` must have exactly "
                                  "one string per column, in column order"),
                Param("highlight_row", ParamType.INT, required=False),
            ),
            min_sec=8, max_sec=90),

        Template(
            name="terminal_replay", version="1.1.0", kind=Kind.SCREEN_DEMO,
            description="Commands and output appearing in sequence. §14.1's "
                        "procedural category — the one Colossyan cannot serve.",
            params=(
                Param("steps", ParamType.STEP_LIST, max_items=12,
                      description="each step is a command and its output"),
                Param("caption", ParamType.TEXT, required=False),
            ),
            min_sec=10, max_sec=120),

        Template(
            name="ui_walkthrough", version="1.1.0", kind=Kind.SCREEN_DEMO,
            description="A synthetic interface with a pointer moving through it.",
            params=(
                Param("surface", ParamType.ASSET_REF, required=False,
                      description="screenshot or synthetic UI; absent means drawn"),
                Param("steps", ParamType.STEP_LIST, max_items=8),
            ),
            min_sec=10, max_sec=120),

        Template(
            name="concept_illustration", version="1.2.0", kind=Kind.ILLUSTRATION,
            description="A drawn metaphor for an abstract idea. §4.4 ranks this "
                        "below a rendered diagram — reach for it when there is "
                        "nothing structural to draw.",
            params=(
                Param("subject", ParamType.TEXT, on_screen=False,
                      description="what the illustration DEPICTS — a brief for "
                                  "the artwork, never typeset on screen"),
                # §0's executive decision closes ISSUE-15: for Milestone A this
                # template is typographic and diagrammatic, so it draws a flow
                # of cards and connectors rather than waiting for stock. The
                # asset slot stays architecturally optional so Storyblocks or
                # Freepik can arrive later without redesigning the template.
                Param("steps", ParamType.TEXT_LIST, required=False, max_items=5,
                      description="§9.6: the concept as a vertical flow of "
                                  "labelled blocks, e.g. RAW DATA → FEATURES → "
                                  "MODEL. 3-5 blocks."),
                Param("asset", ParamType.ASSET_REF, required=False,
                      description="optional and future-facing (§0)"),
                Param("caption", ParamType.TEXT, required=False,
                      description="heading above the flow, or the single line "
                                  "when there is no flow"),
            ),
            min_sec=4, max_sec=45),

        Template(
            name="title_card", version="1.2.0", kind=Kind.TITLE_HOOK,
            description="The objective slot's line, typeset. §9.1 reuses the "
                        "objective verbatim as the scene title.",
            params=(
                Param("title", ParamType.TEXT),
                Param("subtitle", ParamType.TEXT, required=False),
                Param("module_label", ParamType.TEXT, required=False,
                      description="§9.2: optional lesson/module label above "
                                  "the title"),
            ),
            min_sec=3, max_sec=15),

        Template(
            name="cold_open", version="1.2.0", kind=Kind.TITLE_HOOK,
            description="A concrete situation before any explanation. §4.4 puts "
                        "stock here specifically: 'a hook at the open, or a "
                        "real-world shot that grounds the problem'.",
            params=(
                Param("premise", ParamType.TEXT, on_screen=False,
                      description="the situation, not the answer — what the "
                                  "shot SHOWS, never typeset on screen"),
                # REQUIRED, and it is the fix for a scene that rendered a blank
                # frame. `premise` is a brief for imagery and `asset` needs an
                # asset pipeline that does not exist yet, so without a headline
                # this template had nothing to draw at all: measured 0.00% ink
                # across three scenes and 33s of the v2 runtime.
                Param("headline", ParamType.TEXT,
                      description="the question or paradox the lesson resolves, "
                                  "held large on screen — design §9.1"),
                Param("module_label", ParamType.TEXT, required=False,
                      description="§9.1: small label above the question, e.g. "
                                  "'MODULE 03 · MODEL EVALUATION'"),
                Param("premise_line", ParamType.TEXT, required=False,
                      description="§9.1: one supporting line under the "
                                  "question, appearing after it is readable"),
                Param("asset", ParamType.ASSET_REF, required=False,
                      description="stock clip; absent means rendered"),
            ),
            min_sec=5, max_sec=20),
    ]
}


class TemplateError(KeyError):
    pass


def get(name: str) -> Template:
    try:
        return TEMPLATES[name]
    except KeyError:
        raise TemplateError(
            f"no template '{name}'. Known: {sorted(TEMPLATES)}") from None


def by_kind(kind: Kind) -> list[Template]:
    return [t for t in TEMPLATES.values() if t.kind is kind]


def fitting(seconds: float, *, signalling: bool | None = None) -> list[Template]:
    """Templates whose duration band contains `seconds`."""
    out = [t for t in TEMPLATES.values() if t.fits(seconds)]
    if signalling is not None:
        out = [t for t in out if t.supports_signalling is signalling]
    return sorted(out, key=lambda t: t.name)


# -------------------------------------------------------------- validation

_LIST_TYPES = {ParamType.TEXT_LIST, ParamType.NODE_LIST, ParamType.EDGE_LIST,
               ParamType.SERIES, ParamType.STEP_LIST, ParamType.ROW_LIST}


def validate_params(template: Template, params: dict) -> list[str]:
    """Check a filled template. Returns problems; empty means usable.

    Deliberately not raising: the visual planner's output goes through the
    linter, which reports rather than throws, and a template filled slightly
    wrong is a finding a human can act on.
    """
    problems: list[str] = []
    unknown = sorted(set(params) - set(template.param_names()))
    for name in unknown:
        problems.append(
            f"{template.name}: unknown parameter '{name}'; it has "
            f"{template.param_names()}")

    for p in template.params:
        if p.name not in params or params[p.name] in (None, "", [], {}):
            if p.required:
                problems.append(f"{template.name}: '{p.name}' is required")
            continue
        value = params[p.name]

        if p.type in _LIST_TYPES:
            if not isinstance(value, list):
                problems.append(f"{template.name}: '{p.name}' must be a list")
                continue
            if p.max_items is not None and len(value) > p.max_items:
                problems.append(
                    f"{template.name}: '{p.name}' has {len(value)} items, "
                    f"more than the {p.max_items} this layout holds legibly")
            problems += _check_list_shape(template, p, value, params)
        elif p.type is ParamType.ENUM:
            if value not in p.choices:
                problems.append(
                    f"{template.name}: '{p.name}' is {value!r}, not one of "
                    f"{list(p.choices)}")
        elif p.type is ParamType.INT:
            if not isinstance(value, int) or isinstance(value, bool):
                problems.append(f"{template.name}: '{p.name}' must be an int")
        elif not isinstance(value, str):
            problems.append(f"{template.name}: '{p.name}' must be a string")

    return problems


def effective_timing_sensitivity(template_name: str,
                                 requested: str) -> tuple[str, str]:
    """What §15.3 sensitivity a scene actually gets, and why.

    Returns `(sensitivity, reason)`. `reason` is empty when the request stands.

    A scene may only be `rigid` if its template declares `intrinsic_tempo`.
    Otherwise the request is downgraded to `elastic` — not silently: the reason
    travels to the CLI and the findings, because a downgrade changes the scene's
    duration and a human should see why.
    """
    if requested != "rigid":
        return requested or "elastic", ""
    try:
        t = get(template_name)
    except KeyError:
        return "elastic", (f"template {template_name!r} is unknown, so no "
                           f"intrinsic tempo can be claimed for it")
    if t.intrinsic_tempo:
        return "rigid", ""
    return "elastic", (
        f"'{t.name}' has no intrinsic tempo — its motion is proportional to the "
        f"duration it is given — so a rigid scene would hold silence to protect "
        f"a tempo that does not exist (§15.3)")


def _check_list_shape(template: "Template", p: Param, value: list,
                      params: dict) -> list[str]:
    """Structure the renderer depends on, checked before anything renders.

    A cell count that disagrees with the column count draws a table whose
    headers line up with nothing, and a step naming a track that does not exist
    has no lane to be drawn in. Both used to render "successfully".
    """
    problems: list[str] = []

    if p.type is ParamType.ROW_LIST:
        n_cols = len(params.get("columns") or [])
        for i, row in enumerate(value):
            cells = (row or {}).get("cells") if isinstance(row, dict) else None
            if not isinstance(cells, list) or not all(
                    isinstance(c, str) for c in cells):
                problems.append(
                    f"{template.name}: rows[{i}] needs a `cells` list of "
                    f"strings, one per column. A row packed into one string is "
                    f"a table with no columns.")
                continue
            if n_cols and len(cells) != n_cols:
                problems.append(
                    f"{template.name}: rows[{i}] has {len(cells)} cell(s) but "
                    f"there are {n_cols} column(s); every row must fill every "
                    f"column, in column order")

    if p.type is ParamType.STEP_LIST and "tracks" in template.param_names():
        tracks = [t for t in (params.get("tracks") or []) if isinstance(t, str)]
        for i, step in enumerate(value):
            track = (step or {}).get("track") if isinstance(step, dict) else None
            if not track:
                problems.append(
                    f"{template.name}: steps[{i}] has no `track`; without one "
                    f"it cannot be placed in a lane and the template stops "
                    f"showing the parallelism it exists for")
            elif tracks and track not in tracks:
                problems.append(
                    f"{template.name}: steps[{i}] is on track {track!r}, which "
                    f"is not one of {tracks}")
    return problems


def check_registry() -> list[str]:
    """Invariants every template must hold. Run by the tests and by `doctor`."""
    problems: list[str] = []
    for t in TEMPLATES.values():
        if t.min_sec > t.max_sec:
            problems.append(f"{t.name}: min_sec {t.min_sec} exceeds max_sec {t.max_sec}")
        if t.safe_area.bottom < CAPTION_SAFE_BOTTOM:
            problems.append(
                f"{t.name}: caption safe area reserves {t.safe_area.bottom} of the "
                f"frame bottom, under §16.2's required {CAPTION_SAFE_BOTTOM}")
        if t.renderer != "agnostic":
            problems.append(
                f"{t.name}: renderer is '{t.renderer}'. R8 keeps the scene graph "
                f"renderer-agnostic; a concrete engine here is a coupling.")
        if t.min_font_px < MIN_FONT_PX:
            problems.append(
                f"{t.name}: min_font_px {t.min_font_px} is under §11.6's {MIN_FONT_PX}")
        if not t.params:
            problems.append(f"{t.name}: no parameters — nothing to fill")
    _check_exemptions(problems)
    return problems


# ------------------------------------------------------------- persistence

def _check_exemptions(problems: list[str]) -> None:
    """An exemption switches off a stated spec rule, so it must justify itself.

    A one-word reason is not a reason. This is deliberately picky because the
    cost of a cheap exemption is a rule that stops applying and nobody noticing
    — which is exactly what happened with the old boolean (ISSUE-13).
    """
    for t in TEMPLATES.values():
        reason = t.signalling_exemption
        if reason and len(reason.split()) < 6:
            problems.append(
                f"{t.name}: signalling_exemption must say WHY this template "
                f"cannot host a cue, in a sentence a reviewer can argue with. "
                f"Got {reason!r}. §9.2 says 'never zero' without exceptions, so "
                f"an exemption is an override of the spec.")


def sync(conn) -> int:
    """Upsert the registry into `templates` (migration 0001 + 0005).

    The code is the source of truth and the table is the read model: a template
    is a thing you review in a diff, not a row someone edits in a database.
    """
    n = 0
    for t in TEMPLATES.values():
        db.execute(conn, """
            insert into templates(name, version, kind, description, param_schema,
                                  min_sec, max_sec, supports_signaling,
                                  caption_safe_area, renderer, min_font_px)
            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            on conflict (name, version) do update set
                kind = excluded.kind,
                description = excluded.description,
                param_schema = excluded.param_schema,
                min_sec = excluded.min_sec,
                max_sec = excluded.max_sec,
                supports_signaling = excluded.supports_signaling,
                caption_safe_area = excluded.caption_safe_area,
                renderer = excluded.renderer,
                min_font_px = excluded.min_font_px
        """, (t.name, t.version, t.kind.value, t.description,
              json.dumps(t.param_schema()), t.min_sec, t.max_sec,
              t.supports_signalling, json.dumps(t.safe_area.to_json()),
              t.renderer, t.min_font_px))
        n += 1
    return n


def load_all(conn) -> list[dict]:
    return db.query(conn, """
        select name, version, kind, min_sec, max_sec, supports_signaling,
               caption_safe_area, renderer, min_font_px, param_schema
          from templates order by kind, name""")

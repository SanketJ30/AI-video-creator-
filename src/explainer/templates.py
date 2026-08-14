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
    supports_signalling: bool
    safe_area: SafeArea = field(default_factory=SafeArea)
    renderer: str = "agnostic"
    min_font_px: int = MIN_FONT_PX

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
            name="labelled_diagram", version="1.0.0", kind=Kind.ANIMATED_DIAGRAM,
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
            min_sec=8, max_sec=120, supports_signalling=True),

        Template(
            name="state_timeline", version="1.0.0", kind=Kind.ANIMATED_DIAGRAM,
            description="Parallel tracks advancing through time — two sessions, "
                        "two threads, a before/after. The one template where the "
                        "referent genuinely changes over time (§8).",
            params=(
                Param("tracks", ParamType.TEXT_LIST, max_items=4,
                      description="one label per lane; 4 is the §9.3 text-bearing cap"),
                Param("steps", ParamType.STEP_LIST, max_items=10,
                      description="ordered events across the tracks"),
                Param("invariant", ParamType.TEXT, required=False,
                      description="a rule shown holding, then breaking"),
            ),
            min_sec=15, max_sec=120, supports_signalling=True),

        Template(
            name="key_phrase", version="1.0.0", kind=Kind.KINETIC_TYPE,
            description="One phrase, typeset large. §9.4's abridged near-paraphrase "
                        "lives here — never a full narration sentence.",
            params=(
                Param("phrase", ParamType.TEXT,
                      description="≤20% of the scene's narration word count (§9.4)"),
                Param("emphasis", ParamType.TEXT, required=False,
                      description="the word carrying the stress"),
            ),
            min_sec=3, max_sec=20, supports_signalling=False),

        Template(
            name="term_card", version="1.0.0", kind=Kind.KINETIC_TYPE,
            description="A term, its one-line characteristic, and an icon. §9.2's "
                        "pre-training rule emits this when a scene introduces ≥3 "
                        "new terms.",
            params=(
                Param("term", ParamType.TEXT),
                Param("characteristic", ParamType.TEXT,
                      description="one line, not a dictionary definition"),
                Param("icon", ParamType.ASSET_REF, required=False),
            ),
            min_sec=4, max_sec=15, supports_signalling=False),

        Template(
            name="series_build", version="1.0.0", kind=Kind.DATA_VIZ,
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
            min_sec=8, max_sec=90, supports_signalling=True),

        Template(
            name="table_build", version="1.0.0", kind=Kind.DATA_VIZ,
            description="Rows revealed in order. Comparison where the cells are "
                        "the content.",
            params=(
                Param("columns", ParamType.TEXT_LIST, max_items=4,
                      description="4 is the §9.3 cap when objects carry text"),
                Param("rows", ParamType.TEXT_LIST, max_items=8),
                Param("highlight_row", ParamType.INT, required=False),
            ),
            min_sec=8, max_sec=90, supports_signalling=True),

        Template(
            name="terminal_replay", version="1.0.0", kind=Kind.SCREEN_DEMO,
            description="Commands and output appearing in sequence. §14.1's "
                        "procedural category — the one Colossyan cannot serve.",
            params=(
                Param("steps", ParamType.STEP_LIST, max_items=12,
                      description="each step is a command and its output"),
                Param("caption", ParamType.TEXT, required=False),
            ),
            min_sec=10, max_sec=120, supports_signalling=True),

        Template(
            name="ui_walkthrough", version="1.0.0", kind=Kind.SCREEN_DEMO,
            description="A synthetic interface with a pointer moving through it.",
            params=(
                Param("surface", ParamType.ASSET_REF, required=False,
                      description="screenshot or synthetic UI; absent means drawn"),
                Param("steps", ParamType.STEP_LIST, max_items=8),
            ),
            min_sec=10, max_sec=120, supports_signalling=True),

        Template(
            name="concept_illustration", version="1.0.0", kind=Kind.ILLUSTRATION,
            description="A drawn metaphor for an abstract idea. §4.4 ranks this "
                        "below a rendered diagram — reach for it when there is "
                        "nothing structural to draw.",
            params=(
                Param("subject", ParamType.TEXT, on_screen=False,
                      description="what the illustration DEPICTS — a brief for "
                                  "the artwork, never typeset on screen"),
                Param("asset", ParamType.ASSET_REF, required=False),
                Param("caption", ParamType.TEXT, required=False,
                      description="the only text a viewer reads on this template"),
            ),
            min_sec=4, max_sec=45, supports_signalling=False),

        Template(
            name="title_card", version="1.0.0", kind=Kind.TITLE_HOOK,
            description="The objective slot's line, typeset. §9.1 reuses the "
                        "objective verbatim as the scene title.",
            params=(
                Param("title", ParamType.TEXT),
                Param("subtitle", ParamType.TEXT, required=False),
            ),
            min_sec=3, max_sec=15, supports_signalling=False),

        Template(
            name="cold_open", version="1.0.0", kind=Kind.TITLE_HOOK,
            description="A concrete situation before any explanation. §4.4 puts "
                        "stock here specifically: 'a hook at the open, or a "
                        "real-world shot that grounds the problem'.",
            params=(
                Param("premise", ParamType.TEXT, on_screen=False,
                      description="the situation, not the answer — what the "
                                  "shot SHOWS, never typeset on screen"),
                Param("asset", ParamType.ASSET_REF, required=False,
                      description="stock clip; absent means rendered"),
            ),
            min_sec=5, max_sec=20, supports_signalling=False),
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
               ParamType.SERIES, ParamType.STEP_LIST}


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
    return problems


# ------------------------------------------------------------- persistence

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

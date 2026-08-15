"""The design tokens, read from the renderer's own token file.

`render/src/tokens.ts` is the single source of truth for every size, space and
canvas dimension (design system §3–§6). The linter needs those numbers to decide
whether a scene's content fits, and copying them into Python would create a
second source that drifts the first time someone edits one and not the other.

So they are **parsed** from the TypeScript. The parse is deliberately strict:
a missing role raises at import rather than defaulting, because a silently
defaulted type size would make the fit check measure a layout the renderer is
not producing.

## What this module can and cannot know

It knows the type scale, the content region and the spacing scale. It does
**not** know how a given template arranges its slots — that lives in
`Scene.tsx`, and reproducing it here would be a second renderer. `SLOT_ROLES`
below is an explicit MODEL of the renderer's typography, kept small and tested
against the registry, and its limits are stated where they bite.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

TOKENS_TS = Path("render/src/tokens.ts")


class TokenError(RuntimeError):
    """The token file could not be read as expected."""


@dataclass(frozen=True)
class TypeRole:
    name: str
    size: int
    weight: int
    line: float


def _read() -> str:
    if not TOKENS_TS.exists():
        raise TokenError(
            f"{TOKENS_TS} not found. The design tokens are the source of truth "
            f"for the fit check; without them the linter would be measuring a "
            f"layout nobody specified.")
    return TOKENS_TS.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def type_scale() -> dict[str, TypeRole]:
    """§6's roles, as the renderer defines them."""
    src = _read()
    out: dict[str, TypeRole] = {}
    for m in re.finditer(
            r"(\w+): \{ size: (\d+), weight: (\d+), line: ([\d.]+) \}", src):
        name, size, weight, line = m.groups()
        out[name] = TypeRole(name, int(size), int(weight), float(line))
    if not out:
        raise TokenError("no type roles parsed from tokens.ts")
    return out


@lru_cache(maxsize=1)
def canvas() -> dict[str, int]:
    src = _read()
    block = re.search(r"export const canvas = \{(.*?)\} as const;", src, re.S)
    if not block:
        raise TokenError("no canvas block in tokens.ts")
    values = {k: int(v) for k, v in
              re.findall(r"(\w+): (\d+)", block.group(1))}
    for required in ("width", "height", "marginLeft", "marginRight",
                     "marginTop", "captionZone", "marginBottom", "columns",
                     "gutter"):
        if required not in values:
            raise TokenError(f"canvas.{required} missing from tokens.ts")
    return values


def content_width() -> int:
    c = canvas()
    return c["width"] - c["marginLeft"] - c["marginRight"]


def content_height() -> int:
    c = canvas()
    return c["height"] - c["marginTop"] - c["captionZone"] - c["marginBottom"]


@lru_cache(maxsize=1)
def spacing_scale() -> tuple[int, ...]:
    m = re.search(r"SPACING_SCALE = \[([^\]]+)\]", _read())
    if not m:
        raise TokenError("no SPACING_SCALE in tokens.ts")
    return tuple(int(x) for x in re.findall(r"\d+", m.group(1)))


@lru_cache(maxsize=1)
def min_font_px() -> int:
    m = re.search(r"MIN_FONT_PX = (\d+)", _read())
    if not m:
        raise TokenError("no MIN_FONT_PX in tokens.ts")
    return int(m.group(1))


# ===========================================================================
# AUTHORED AND UNREVIEWED — one number, and it is a measurement parameter
# rather than a design value.
#
# Average glyph advance as a fraction of font size, used to estimate how many
# characters fit on a line. Inter's mixed-case average sits near 0.5 em; the
# design spec gives no such figure because it is a property of the typeface,
# not of the system.
#
# It only ever feeds an ESTIMATE. Every finding derived from it says so, and
# `FIT_TOLERANCE` below keeps a marginal case from blocking on arithmetic this
# rough.
# ===========================================================================
AUTHORED_GLYPH_ADVANCE = 0.5

# A scene must exceed the content region by more than this before the fit check
# blocks. Estimating within 15% is about as well as a character-count model can
# do, and blocking a scene that actually fits is worse than missing one that
# marginally does not — the author would have no way to satisfy the gate.
AUTHORED_FIT_TOLERANCE = 0.15


# How each template's slots are typeset. A MODEL of `Scene.tsx`, not a copy of
# it: the sizes come from the shared token file, but which role a slot uses is
# stated here and in the renderer, and the two must move together. A test
# asserts every registered template has an entry and every role exists.
SLOT_ROLES: dict[str, dict[str, str]] = {
    "cold_open": {"headline": "display"},
    "title_card": {"title": "h1", "subtitle": "body"},
    "key_phrase": {"phrase": "display", "emphasis": "body"},
    "term_card": {"term": "h1", "characteristic": "body"},
    "concept_illustration": {"caption": "h2"},
    "labelled_diagram": {"title": "h2", "nodes": "h3", "edges": "caption"},
    "state_timeline": {"tracks": "label", "steps": "body",
                       "invariant": "bodyStrong"},
    "table_build": {"columns": "label", "rows": "body"},
    "series_build": {"title": "h2", "series": "body"},
    "terminal_replay": {"steps": "mono", "caption": "caption"},
    "ui_walkthrough": {"steps": "body"},
}


@dataclass(frozen=True)
class FitEstimate:
    """How much vertical room a scene's typeset content needs."""

    needed_px: int
    available_px: int
    overflow_px: int
    lines: int
    detail: list[str]

    @property
    def fits(self) -> bool:
        return self.overflow_px <= 0

    @property
    def overflow_share(self) -> float:
        return self.overflow_px / self.available_px if self.available_px else 0.0


def _lines_for(text: str, role: TypeRole, width: int) -> int:
    per_line = max(1, int(width / (role.size * AUTHORED_GLYPH_ADVANCE)))
    return max(1, math.ceil(len(text) / per_line))


def estimate_fit(template_name: str, slots: dict) -> FitEstimate:
    """Estimate whether a filled template's text fits the content region.

    Character-count based, and therefore an estimate: it does not know the
    renderer's exact line breaking, does not account for a grid that puts two
    slots side by side, and cannot see a template's own internal padding. It is
    sized to catch "this scene has far too much copy", which is the failure §6
    is about, not to predict a two-pixel overflow.
    """
    roles = type_scale()
    mapping = SLOT_ROLES.get(template_name, {})
    width = content_width()
    available = content_height()

    total = 0
    lines = 0
    detail: list[str] = []
    for slot, role_name in mapping.items():
        value = slots.get(slot)
        if value in (None, "", [], {}):
            continue
        role = roles.get(role_name)
        if role is None:
            raise TokenError(
                f"{template_name}.{slot} maps to type role {role_name!r}, "
                f"which tokens.ts does not define")

        items = value if isinstance(value, list) else [value]
        slot_lines = 0
        for item in items:
            text = _text_of(item)
            if text:
                slot_lines += _lines_for(text, role, width)
        if not slot_lines:
            continue
        height = int(slot_lines * role.size * role.line)
        total += height
        lines += slot_lines
        detail.append(f"{slot}({role_name}): {slot_lines} line(s), ~{height}px")

    return FitEstimate(needed_px=total, available_px=available,
                       overflow_px=max(0, total - available), lines=lines,
                       detail=detail)


def _text_of(item) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for key in ("label", "text", "cells", "detail"):
            v = item.get(key)
            if isinstance(v, str):
                return v
            if isinstance(v, list):
                return " ".join(str(x) for x in v)
    return ""

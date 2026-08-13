"""The stage handler contract.

A handler is a pure-ish function: given a fully resolved set of upstream
artifacts and a pinned prompt/model/config, produce bytes. It must NOT read the
database, must not decide whether it should run (the orchestrator already
decided), and must not embed wall-clock time, run ids or random seeds in its
output — anything nondeterministic in the bytes destroys byte-identity across
cache hits, which is the property Gate C trust rests on (§5.1).

If a stage genuinely needs randomness (3 hook variants), the seed is an INPUT:
put it in the closure via `extra`, so the same seed reproduces the same output.

THE ONE RULE: a handler may only read what its StageSpec declares — upstream
artifacts, the prompt, `ctx.config` (from `config_keys`), `ctx.beat.inputs` (from
`reads_beat_inputs`) and the video fields named in `video_input_keys`. Reading
anything else — say `ctx.video["title"]` without declaring it — produces output
that depends on an input outside the hash closure, which means a stale cache hit
the moment that field changes. The artifact store catches this on write and
raises rather than silently corrupting the cache; if you see StoreError about
differing bytes for one hash, this rule is what you broke.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable

from ..dag import BeatRef, Node, StageSpec


class StageNotImplemented(RuntimeError):
    """Raised for a declared-but-unbuilt stage. Carries the PRD pointer."""


class StageFailure(RuntimeError):
    """A real failure. `error_class` drives the retry policy in §6.4."""

    def __init__(self, message: str, error_class: str = "unknown"):
        super().__init__(message)
        self.error_class = error_class


@dataclass
class LoadedInput:
    label: str
    hash: str
    mime: str
    data: bytes

    def json(self):
        return json.loads(self.data.decode())

    def text(self) -> str:
        return self.data.decode()


@dataclass
class StageContext:
    node: Node
    spec: StageSpec
    hash: str
    series: dict
    video: dict
    beat: BeatRef | None
    inputs: dict[str, LoadedInput]
    prompt_body: str | None
    prompt_version: str | None
    model_version: str | None
    config: dict

    def inp(self, label: str) -> LoadedInput:
        try:
            return self.inputs[label]
        except KeyError:
            raise StageFailure(
                f"{self.node.key}: missing upstream input '{label}'; have "
                f"{sorted(self.inputs)}", "internal") from None

    def inputs_like(self, prefix: str) -> list[LoadedInput]:
        return [v for k, v in sorted(self.inputs.items()) if k.startswith(prefix)]


@dataclass
class StageResult:
    data: bytes
    mime: str = "application/json"
    cost_usd: float = 0.0
    duration_ms: int | None = None
    model_version: str | None = None
    meta: dict = field(default_factory=dict)

    @classmethod
    def from_json(cls, obj, **kw) -> "StageResult":
        # sort_keys + fixed indent: two runs with equal content give equal bytes
        return cls(json.dumps(obj, indent=2, sort_keys=True).encode(), "application/json", **kw)


Handler = Callable[[StageContext], StageResult]
_REGISTRY: dict[str, dict[str, Handler]] = {}


def handler(graph: str, stage: str) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        _REGISTRY.setdefault(graph, {})[stage] = fn
        return fn
    return deco


def get_handler(graph: str, stage: str) -> Handler:
    try:
        return _REGISTRY[graph][stage]
    except KeyError:
        raise StageNotImplemented(
            f"stage '{stage}' has no handler in graph '{graph}'. "
            f"Register one with @handler('{graph}', '{stage}') in "
            f"src/explainer/stages/. See docs/prd/PRD_v4.md for its spec."
        ) from None


def has_handler(graph: str, stage: str) -> bool:
    return stage in _REGISTRY.get(graph, {})

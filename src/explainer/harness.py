"""The regression harness (Sequence v0.2 §14.4).

    §14.4 makes this the instrument that validates every prompt change in the
    product. It has to be trustworthy before anything is measured with it.

## Why 3 samples, and why 2 of 3

Week 3 recorded a series of findings from one extraction run per configuration:
v1 was "too granular", a brief edit "closed the anomaly gap", a topic clause
"starved the criterion". Then two samples of one fixed configuration disagreed
more than any two configurations had — 2 of 3 anomaly names on one draw, 0 of 3
on the next, same brief, same prompt, same model. Every n=1 comparison in the
record was indistinguishable from sampling noise.

Sanket's threshold, and his reasoning, recorded because the number matters less
than why it was chosen:

    3 samples per configuration; a check passes if met in at least 2 of 3.
    3 is the smallest n that admits a majority, and at roughly $0.10 a call it
    stays cheap enough to run on every prompt change — which matters more here
    than statistical elegance. A finding that cannot survive 2-of-3 is not a
    finding.

This is not a claim that 3 samples is statistically sufficient. It is a claim
that 1 is demonstrably insufficient and that 3 is affordable on every change. A
check that lands 2/3 twice in a row is worth more than one that lands 3/3 once.

## What a check is

Deterministic, computed from the extracted graph, no model call — same rule as
every other gate in this codebase (§7.1 rule 4). A check that needed a model to
decide would make the harness a matter of opinion, which is exactly the property
it exists to remove.

Checks are declared in the alignment file so the pass criterion is a human's
stated intent rather than something the code decided, and are looked up here by
name. Adding a check means adding a function here AND naming it in the file.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from .agents import objective_extractor as ox
from .brief import CourseBrief
from .objectives import Bloom, Objective

DEFAULT_SAMPLES = 3
DEFAULT_PASS_K = 2


# --------------------------------------------------------------- the checks

def _corpus(objectives: list[Objective], taught_only: bool = False) -> str:
    """All the prose an objective carries, lowercased, for term checks."""
    pool = [o for o in objectives if not (taught_only and o.assumed)]
    return " ".join(
        " ".join(filter(None, [o.verb, o.object, o.condition or "", o.criterion or ""]))
        for o in pool).lower()


def check_mentions_all(objectives: list[Objective], terms: list[str],
                       **_) -> tuple[bool, str]:
    """Every term appears somewhere in the objective prose. Word-boundary
    matched: a bare substring test reported 'ssi' present because 'sessions'
    contains it."""
    text = _corpus(objectives)
    missing = [t for t in terms
               if not re.search(rf"\b{re.escape(t.lower())}", text)]
    return (not missing,
            "all present" if not missing else f"missing: {', '.join(missing)}")


def check_mentions_none(objectives: list[Objective], terms: list[str],
                        **_) -> tuple[bool, str]:
    text = _corpus(objectives)
    found = [t for t in terms if re.search(rf"\b{re.escape(t.lower())}", text)]
    return (not found,
            "none present" if not found else f"present: {', '.join(found)}")


def check_taught_count(objectives: list[Objective], min: int = 1,
                       max: int = 2, **_) -> tuple[bool, str]:
    n = len([o for o in objectives if not o.assumed])
    return (min <= n <= max, f"{n} taught objectives (want {min}-{max})")


def check_max_taught_bloom(objectives: list[Objective], level: str = "analyze",
                           **_) -> tuple[bool, str]:
    taught = [o for o in objectives if not o.assumed]
    if not taught:
        return False, "no taught objectives"
    top = max(taught, key=lambda o: o.bloom_level.rank)
    want = Bloom(level)
    return (top.bloom_level is want,
            f"highest taught bloom is {top.bloom_level.value} (want {want.value})")


def check_no_blocking_findings(objectives: list[Objective], report=None,
                               **_) -> tuple[bool, str]:
    if report is None:
        return True, "no report supplied"
    return (report.ok,
            "clean" if report.ok else
            f"{len(report.blocking)} blocking: "
            f"{', '.join(f.rule for f in report.blocking)}")


CHECKS: dict[str, Callable[..., tuple[bool, str]]] = {
    "mentions_all": check_mentions_all,
    "mentions_none": check_mentions_none,
    "taught_count": check_taught_count,
    "max_taught_bloom": check_max_taught_bloom,
    "no_blocking_findings": check_no_blocking_findings,
}


class UnknownCheck(KeyError):
    pass


def run_check(name: str, objectives: list[Objective], params: dict,
              report=None) -> tuple[bool, str]:
    try:
        fn = CHECKS[name]
    except KeyError:
        raise UnknownCheck(
            f"no check '{name}'. Known: {sorted(CHECKS)}. A check must be a "
            f"deterministic function of the extracted graph — if it needs a "
            f"model to decide, it does not belong in the harness."
        ) from None
    return fn(objectives, report=report, **params)


# ------------------------------------------------------------------ results

@dataclass
class CheckSpec:
    name: str
    params: dict = field(default_factory=dict)
    label: str = ""

    @property
    def key(self) -> str:
        return self.label or self.name


@dataclass
class SampleResult:
    n: int
    objectives: list[Objective]
    cost_usd: float
    attempts: int
    checks: dict[str, tuple[bool, str]] = field(default_factory=dict)
    report_ok: bool = True


@dataclass
class HarnessResult:
    config: str
    prompt_version: str
    brief_version: int
    samples: list[SampleResult] = field(default_factory=list)
    pass_k: int = DEFAULT_PASS_K
    specs: list[CheckSpec] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.samples)

    @property
    def cost_usd(self) -> float:
        return round(sum(s.cost_usd for s in self.samples), 6)

    def hits(self, key: str) -> int:
        return sum(1 for s in self.samples if s.checks.get(key, (False, ""))[0])

    def passed(self, key: str) -> bool:
        return self.hits(key) >= self.pass_k

    def verdict(self, key: str) -> str:
        k = self.hits(key)
        return f"met in {k} of {self.n} — {'PASSES' if self.passed(key) else 'FAILS'}"

    def render(self) -> str:
        out = [f"{self.config}: {self.n} samples, prompt {self.prompt_version}, "
               f"brief v{self.brief_version}, ${self.cost_usd:.4f}",
               f"pass criterion: met in at least {self.pass_k} of {self.n}"]
        for spec in self.specs:
            key = spec.key
            out.append(f"  {key}")
            for s in self.samples:
                ok, detail = s.checks.get(key, (False, "not run"))
                out.append(f"      sample {s.n}: {'PASS' if ok else 'fail'}  {detail}")
            out.append(f"      -> {self.verdict(key)}")
        counts = [len([o for o in s.objectives if not o.assumed]) for s in self.samples]
        out.append(f"  taught objective counts across samples: {counts}")
        return "\n".join(out)

    def to_yaml_fragment(self) -> str:
        """The block to append to the alignment file. Emitted rather than
        written so a human reviews it before it becomes the record."""
        lines = [f"    samples: {self.n}",
                 f"    pass_criterion: met in at least {self.pass_k} of {self.n}",
                 f"    harness_cost_usd: {self.cost_usd:.4f}",
                 "    checks:"]
        for spec in self.specs:
            key = spec.key
            lines.append(f"      - name: {spec.name}")
            if spec.label:
                lines.append(f"        label: {spec.label}")
            if spec.params:
                lines.append(f"        params: {spec.params}")
            results = [str(s.checks.get(key, (False, ""))[0]).lower()
                       for s in self.samples]
            lines.append(f"        results: [{', '.join(results)}]")
            lines.append(f"        verdict: {self.verdict(key)}")
        return "\n".join(lines)


# ------------------------------------------------------------------- runner

def run(conn, course_id: str | None, brief: CourseBrief, specs: list[CheckSpec], *,
        config: str, samples: int = DEFAULT_SAMPLES, pass_k: int = DEFAULT_PASS_K,
        prompt_version: int | None = None, client=None,
        model: str | None = None, on_sample=None) -> HarnessResult:
    """Run `samples` extractions of one configuration and score every check.

    Each sample is an independent call — no caching of the result, no reuse.
    That is the point: the harness measures the spread, and a cached second
    sample would report a spread of zero.
    """
    result = HarnessResult(config=config, prompt_version="", brief_version=brief.version,
                           pass_k=pass_k, specs=specs)
    for i in range(1, samples + 1):
        outcome = ox.extract(conn, course_id, brief, client=client, model=model,
                             prompt_version=prompt_version)
        result.prompt_version = outcome.provenance["prompt_version"]
        sample = SampleResult(
            n=i, objectives=outcome.objectives, cost_usd=outcome.cost_usd,
            attempts=len(outcome.attempts), report_ok=outcome.report.ok)
        for spec in specs:
            sample.checks[spec.key] = run_check(
                spec.name, outcome.objectives, spec.params, outcome.report)
        result.samples.append(sample)
        if on_sample:
            on_sample(sample, result)
    return result


def specs_from_yaml(raw: list[dict]) -> list[CheckSpec]:
    return [CheckSpec(name=str(c["name"]), params=dict(c.get("params") or {}),
                      label=str(c.get("label") or "")) for c in raw]

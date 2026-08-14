"""Objective extraction against the hand-authored gold graph.

Two layers, on purpose:

  * The parse / repair / escalate loop is tested offline with a scripted fake
    client. Those tests are deterministic and always run: they are what stops a
    refactor from quietly turning a schema failure into a silent empty graph.

  * The extraction itself runs against the real pinned model and diffs the
    result against `tests/gold/mvcc_write_skew.yaml`. It needs credentials and
    costs money, so it skips without an API key rather than failing the suite —
    but the tolerance it asserts is the real bar:

        all 4 gold objectives found
        the o1 -> o2 -> o3 -> o4 chain intact as DIRECT edges
        no Bloom level off by more than one

Run it explicitly with:  pytest -m live tests/test_objective_extraction.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from explainer import goldgraph
from explainer.agents import objective_extractor as ox
from explainer.brief import Audience, CourseBrief
from explainer.escalation import Escalated
from explainer.objectives import Bloom

GOLD_PATH = Path(__file__).parent / "gold" / "mvcc_write_skew.yaml"
# The gold's v3 amendment merged the old o2 and o3 into one
# analyze-level objective; the chain lost a link.
CHAIN = ["o1", "o2", "o4"]


# ------------------------------------------------------------------ fixtures

def mvcc_brief() -> CourseBrief:
    """The Course Brief for the gold topic.

    Built from the gold file's own `topic` and `audience` so there is exactly
    one source of truth: if the brief and the gold graph could drift apart, a
    passing diff would prove nothing.
    """
    gold = goldgraph.load_gold(GOLD_PATH)
    aud = gold.audience or {}
    return CourseBrief(
        title="MVCC and write skew",
        description=gold.topic,
        audience=Audience(
            level=aud.get("level", "intermediate"),
            prior_knowledge=tuple(aud.get("prior_knowledge") or ()),
            native_language_ratio=float(aud.get("native_language_ratio") or 0.0),
        ),
        source_material=(f"engine:{gold.engine}",) if gold.engine else (),
    )


class FakeMessages:
    """Replays a scripted list of responses. One entry per expected call."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("extractor made more calls than the script allows")
        text = self._responses.pop(0)

        class _Block:
            type = "text"

            def __init__(self, t):
                self.text = t

        class _Usage:
            input_tokens = 100
            output_tokens = 200

        class _Resp:
            stop_reason = "end_turn"
            content = [_Block(text)]
            usage = _Usage()

        return _Resp()

    def stream(self, **kwargs):
        """Agents that stream (script_writer) go through here; the recorded
        call shape is identical, so assertions on .calls work either way."""
        return _FakeStream(self.create(**kwargs))


class _FakeStream:
    """Context manager mirroring client.messages.stream()."""

    def __init__(self, resp):
        self._resp = resp

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self._resp


class FakeClient:
    def __init__(self, responses: list[str]):
        self.messages = FakeMessages(responses)


def _graph_json(**overrides) -> str:
    doc = {
        "objectives": [
            {"ref": "o1", "verb": "explain",
             "object": "how snapshot isolation gives each transaction a consistent view",
             "condition": "", "criterion": "", "bloom_level": "understand",
             "knowledge_type": "conceptual", "assumed": True, "prerequisites": [],
             "rationale": "the foundation the rest stands on",
             "learner_facing_statement": "You'll see how a snapshot freezes what a transaction reads."},
            {"ref": "o2", "verb": "describe",
             "object": "which anomalies PostgreSQL Repeatable Read prevents",
             "condition": "", "criterion": "", "bloom_level": "understand",
             "knowledge_type": "conceptual", "assumed": False, "prerequisites": ["o1"],
             "rationale": "needed before write skew makes sense",
             "learner_facing_statement": "You'll name which anomalies Repeatable Read stops."},
        ],
        "assessment_items": [
            {"ref": "a1", "objective_ref": "o2", "bloom_level": "understand",
             "kind": "mcq", "stem": "Which anomaly does Repeatable Read still permit?"},
        ],
    }
    doc.update(overrides)
    return json.dumps(doc)


# --------------------------------------------------------- gold file itself

def test_gold_file_parses_and_is_internally_consistent():
    gold = goldgraph.load_gold(GOLD_PATH)
    assert [o.ref for o in gold.objectives] == CHAIN
    assert gold.edges() == {("o1", "o2"), ("o2", "o4")}
    assert gold.by_ref()["o1"].assumed is True
    assert gold.scope["o4"] is False, "o4 is video 2, out of Milestone A"
    assert gold.notes, "the gold file's extraction notes are part of the standard"


def test_gold_graph_passes_the_deterministic_checks():
    """The gold file must itself survive objectives.validate() — modulo the
    assessment items the author has flagged as TODO. If the human-authored
    standard cannot pass its own linter, the linter is wrong."""
    from explainer.objectives import validate
    gold = goldgraph.load_gold(GOLD_PATH)
    r = validate(gold.objectives, items=gold.items)
    assert r.ok, r.render()
    assert r.teaching_order == CHAIN


# ------------------------------------------------------- diff, offline

def test_diff_is_clean_against_itself():
    gold = goldgraph.load_gold(GOLD_PATH)
    d = goldgraph.diff(gold.objectives, gold)
    assert not d.missing and not d.extra
    assert not d.bloom and not d.missing_edges and not d.extra_edges
    assert d.chain_intact(CHAIN)


def test_diff_catches_a_flattened_chain():
    """The failure the gold file's own note calls out: an extractor that keeps
    every objective but drops the sequencing."""
    gold = goldgraph.load_gold(GOLD_PATH)
    flat = [
        type(o)(ref=o.ref, verb=o.verb, object=o.object, bloom_level=o.bloom_level,
                knowledge_type=o.knowledge_type, condition=o.condition,
                criterion=o.criterion, prerequisites=[], assumed=o.assumed)
        for o in gold.objectives
    ]
    d = goldgraph.diff(flat, gold)
    assert not d.missing, "all four objectives are still present"
    assert d.missing_edges == [("o1", "o2"), ("o2", "o4")]
    assert not d.chain_intact(CHAIN)


def test_diff_matches_on_content_not_on_ref():
    """Refs are arbitrary labels; a renumbered graph is not a wrong graph."""
    gold = goldgraph.load_gold(GOLD_PATH)
    renamed = []
    remap = {"o1": "L3", "o2": "L2", "o4": "L1"}
    for o in gold.objectives:
        renamed.append(type(o)(
            ref=remap[o.ref], verb=o.verb, object=o.object,
            bloom_level=o.bloom_level, knowledge_type=o.knowledge_type,
            condition=o.condition, criterion=o.criterion,
            prerequisites=[remap[p] for p in o.prerequisites], assumed=o.assumed))
    d = goldgraph.diff(renamed, gold)
    assert d.mapping == remap
    assert not d.missing_edges and d.chain_intact(CHAIN)


def test_diff_reports_a_bloom_level_that_is_off_by_one():
    gold = goldgraph.load_gold(GOLD_PATH)
    objs = list(gold.objectives)
    o2 = objs[1]
    objs[1] = type(o2)(ref=o2.ref, verb="compare", object=o2.object,
                       bloom_level=Bloom.EVALUATE, knowledge_type=o2.knowledge_type,
                       condition=o2.condition, criterion=o2.criterion,
                       prerequisites=o2.prerequisites, assumed=o2.assumed)
    d = goldgraph.diff(objs, gold)
    assert [m.gold_ref for m in d.bloom] == ["o2"]
    assert d.max_bloom_distance == 1


# --------------------------------------------- parse / repair / escalate

def test_parse_accepts_a_well_formed_graph():
    objs, items, rationales, out_of_scope, learner_facing = ox.parse(_graph_json())
    assert [o.ref for o in objs] == ["o1", "o2"]
    assert objs[0].assumed is True
    assert objs[1].prerequisites == ["o1"]
    assert items[0].bloom_level is Bloom.UNDERSTAND
    assert rationales["o1"]
    assert learner_facing["o1"].startswith("You'll")


def test_parse_collects_every_problem_at_once():
    """One repair round trip must be able to fix everything, not peel errors
    off one call at a time."""
    bad = json.dumps({
        "objectives": [
            {"ref": "o1", "verb": "explain", "object": "x", "condition": "",
             "criterion": "", "bloom_level": "vibes", "knowledge_type": "conceptual",
             "assumed": False, "prerequisites": [], "rationale": "",
             "learner_facing_statement": "You'll do the thing."},
            {"ref": "o2", "verb": "describe", "object": "y", "condition": "",
             "criterion": "", "bloom_level": "understand", "knowledge_type": "nonsense",
             "assumed": False, "prerequisites": [], "rationale": "",
             "learner_facing_statement": "You'll do the other thing."},
        ],
        "assessment_items": [],
    })
    with pytest.raises(ox.SchemaError) as e:
        ox.parse(bad)
    assert len(e.value.problems) == 2
    assert "bloom_level" in e.value.problems[0]
    assert "knowledge_type" in e.value.problems[1]


def test_parse_rejects_a_dangling_assessment_target():
    bad = _graph_json(assessment_items=[
        {"ref": "a1", "objective_ref": "o9", "bloom_level": "apply",
         "kind": "predict", "stem": "?"}])
    with pytest.raises(ox.SchemaError) as e:
        ox.parse(bad)
    assert "o9" in str(e.value)


def test_repair_loop_recovers_and_feeds_the_errors_back():
    client = FakeClient(["not json at all", _graph_json()])
    outcome = ox.extract(None, None, mvcc_brief(), client=client)
    assert len(outcome.attempts) == 2
    assert outcome.attempts[0].error and outcome.attempts[1].error is None
    repair_turn = client.messages.calls[1]["messages"][-1]["content"]
    assert "not valid JSON" in repair_turn, "the model must see the actual error"
    assert outcome.provenance["attempt"] == 2


def test_three_bad_responses_escalate_rather_than_returning_nothing():
    """Invariant 7: the failure path ends in a recorded, actionable state."""
    client = FakeClient(["nope"] * 3)
    with pytest.raises(Escalated) as e:
        ox.extract(None, None, mvcc_brief(), client=client)
    assert e.value.error_class == "llm_schema"
    assert e.value.next_step
    assert "last_raw_response" in e.value.offending_input
    assert client.messages.calls.__len__() == 3, "max 2 repairs, then stop"


def test_blocking_findings_are_returned_not_repaired():
    """A pedagogically wrong graph is a report, not a retry. Auto-fixing it
    would hide the exact signal this stage exists to produce."""
    doc = json.loads(_graph_json())
    doc["objectives"][1]["verb"] = "understand"        # banned, blocking
    client = FakeClient([json.dumps(doc)])
    outcome = ox.extract(None, None, mvcc_brief(), client=client)
    assert len(outcome.attempts) == 1, "no repair round trip for a finding"
    assert not outcome.report.ok
    assert any(f.rule == "observable_verb" for f in outcome.report.blocking)


def test_provenance_is_recorded_on_the_outcome():
    client = FakeClient([_graph_json()])
    outcome = ox.extract(None, None, mvcc_brief(), client=client, model="test-model")
    p = outcome.provenance
    assert p["agent"] == "objective_extractor"
    assert p["prompt_version"].startswith("objective_extractor@v")
    assert p["model_version"] == "test-model"
    assert "extracted_at" in p


def test_the_pinned_model_is_used_by_default():
    from explainer.config import settings
    client = FakeClient([_graph_json()])
    ox.extract(None, None, mvcc_brief(), client=client)
    assert client.messages.calls[0]["model"] == settings().models.frontier


def test_the_brief_reaches_the_model_verbatim():
    client = FakeClient([_graph_json()])
    brief = mvcc_brief()
    ox.extract(None, None, brief, client=client)
    sent = client.messages.calls[0]["messages"][0]["content"]
    assert brief.description in sent
    for known in brief.audience.prior_knowledge:
        assert known in sent


# --------------------------------------------------------------- live run

live = pytest.mark.skipif(
    not (os.getenv("ANTHROPIC_API_KEY") and os.getenv("EXPLAINER_LIVE") == "1"),
    reason="live extraction costs a real model call: set EXPLAINER_LIVE=1 "
           "(and ANTHROPIC_API_KEY) to opt in. `make test` must never bill.",
)


@live
@pytest.mark.live
def test_extraction_matches_the_gold_graph_within_tolerance():
    gold = goldgraph.load_gold(GOLD_PATH)
    outcome = ox.extract(None, None, mvcc_brief())
    d = goldgraph.diff(outcome.objectives, gold)

    print("\n" + d.render())          # -s shows the alignment when this fails

    assert not d.missing, (
        f"gold objectives not found: {d.missing}\n{d.render()}")
    assert d.chain_intact(CHAIN), (
        f"the {' -> '.join(CHAIN)} chain is not intact as direct edges\n{d.render()}")
    assert d.max_bloom_distance <= 1, (
        f"a Bloom level is off by more than one\n{d.render()}")


# ------------------------------------------------- hand alignment wiring

ALIGN_PATH = Path(__file__).parent / "gold" / "mvcc_alignment.yaml"


def _obj(ref, verb, text, bloom, ktype, prereqs=(), assumed=False):
    from explainer.objectives import KnowledgeType, Objective
    return Objective(ref=ref, verb=verb, object=text, bloom_level=bloom,
                     knowledge_type=KnowledgeType(ktype), prerequisites=list(prereqs),
                     assumed=assumed)


def test_alignment_file_parses():
    a = goldgraph.load_alignment(ALIGN_PATH)
    v1 = a.by_run("v1-run2")
    assert v1 is not None
    assert v1.coverage["o1"] == ["o1", "o2", "o3", "o4"]
    assert v1.coverage["o3"] == ["o7", "o8"]
    assert v1.coverage_notes["o2"], "the human's comment is part of the record"


def test_diff_without_an_alignment_is_labelled_approximate():
    gold = goldgraph.load_gold(GOLD_PATH)
    d = goldgraph.diff(gold.objectives, gold)
    assert d.approximate and d.method == "approximate"
    assert "APPROXIMATE" in d.render()


def test_an_alignment_for_a_different_run_does_not_silently_apply():
    """The stale-alignment guard: a v1 mapping must not score a v2 extraction.
    Same class of error as a stale cache hit."""
    gold = goldgraph.load_gold(GOLD_PATH)
    a = goldgraph.load_alignment(ALIGN_PATH)
    d = goldgraph.diff(gold.objectives, gold, alignment=a,
                       prompt_version="objective_extractor@v2+deadbeef")
    assert d.approximate, "a v1 entry must not be reused for a v2 run"


def test_hand_alignment_reports_coverage_instead_of_one_to_one_misses():
    """The whole point: 4 gold objectives split across 10 extracted ones are
    covered, not missing — which the scorer cannot express."""
    from explainer.objectives import Bloom as B
    gold = goldgraph.load_gold(GOLD_PATH)
    extracted = [
        _obj("o1", "state", "xid semantics", B.REMEMBER, "factual", assumed=True),
        _obj("o2", "write", "transaction blocks", B.APPLY, "procedural", assumed=True),
        _obj("o3", "explain", "tuple versioning", B.UNDERSTAND, "conceptual", ["o1"]),
        _obj("o4", "identify", "snapshot parts", B.REMEMBER, "factual", ["o3"]),
        _obj("o5", "predict", "which version is visible", B.APPLY, "procedural", ["o4"]),
        _obj("o6", "contrast", "snapshot timing RC vs RR", B.ANALYZE, "conceptual", ["o5"]),
        _obj("o7", "predict", "whether write skew occurs", B.APPLY, "procedural", ["o6"]),
        _obj("o8", "differentiate", "same-row conflict", B.ANALYZE, "conceptual", ["o7"]),
        _obj("o9", "trace", "rw dependencies under SSI", B.ANALYZE, "conceptual", ["o7"]),
        _obj("o10", "recommend", "a remedy", B.EVALUATE, "procedural", ["o8", "o9"]),
    ]
    a = goldgraph.load_alignment(ALIGN_PATH)
    d = goldgraph.diff(extracted, gold, alignment=a,
                       prompt_version="objective_extractor@v1+03930968")
    assert d.method == "hand", "10 objectives on v1 must select the v1-run2 entry"
    assert not d.missing, "every gold objective is covered by some extracted group"
    assert not d.extra
    assert "HAND" in d.render()


def test_a_stale_alignment_raises_rather_than_scoring_around_it():
    gold = goldgraph.load_gold(GOLD_PATH)
    a = goldgraph.load_alignment(ALIGN_PATH)
    entry = a.by_run("v1-run2")
    with pytest.raises(ValueError) as e:
        goldgraph.diff_with_alignment([_obj("zz", "explain", "x", Bloom.UNDERSTAND,
                                            "conceptual")], gold, entry, "test")
    assert "not in this graph" in str(e.value)


# --------------------------------------------------------------- cost model

class _Usage:
    def __init__(self, **kw):
        self.input_tokens = kw.get("input_tokens", 0)
        self.cache_creation_input_tokens = kw.get("cache_creation_input_tokens", 0)
        self.cache_read_input_tokens = kw.get("cache_read_input_tokens", 0)
        self.output_tokens = kw.get("output_tokens", 0)


def test_price_counts_all_four_token_classes():
    """The bug this guards: counting only uncached input under-reported every
    cached run, and got worse the better caching worked."""
    # claude-opus-5 is $5/$25 per MTok.
    cost = ox._price("claude-opus-5", _Usage(
        input_tokens=1_000_000,                  # 1.00x  -> $5.00
        cache_creation_input_tokens=1_000_000,   # 1.25x  -> $6.25
        cache_read_input_tokens=1_000_000,       # 0.10x  -> $0.50
        output_tokens=1_000_000,                 #        -> $25.00
    ))
    assert round(cost, 6) == 36.75


def test_price_ignoring_cache_would_be_lower():
    """Regression direction: the old formula must not be able to creep back."""
    usage = _Usage(input_tokens=310, cache_creation_input_tokens=2000,
                   output_tokens=3022)
    full = ox._price("claude-opus-5", usage)
    uncached_only = (310 * 5 + 3022 * 25) / 1_000_000
    assert full > uncached_only


def test_price_is_zero_for_an_unpriced_model():
    assert ox._price("some-model-we-have-no-rate-for", _Usage(output_tokens=99)) == 0.0


def test_an_objective_outside_the_o_namespace_is_rejected():
    """A real run emitted an objective 'a1' with object "placeholder" and the
    rationale "Not an objective; ignore." It was structurally valid and reached
    the database. The prompt reserves a* for assessment items."""
    doc = json.loads(_graph_json())
    doc["objectives"].append({
        "ref": "a1", "verb": "predict", "object": "placeholder",
        "condition": "", "criterion": "", "bloom_level": "apply",
        "knowledge_type": "procedural", "assumed": True, "prerequisites": [],
        "rationale": "Not an objective; ignore.",
        "learner_facing_statement": "You'll ignore this."})
    with pytest.raises(ox.SchemaError) as e:
        ox.parse(json.dumps(doc))
    assert "outside the objective namespace" in str(e.value)

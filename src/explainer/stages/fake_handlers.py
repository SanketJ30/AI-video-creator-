"""Handlers for the fake graph. No network, no models, fully deterministic.

These exist to prove the machinery, and they stay in the repo forever as the
regression fixture for the invalidation model. Every future change to hashing,
DAG resolution or the worker is validated against `explainer verify` before it
lands.
"""
from __future__ import annotations

import struct

from .base import StageContext, StageResult, handler

G = "fake"


@handler(G, "research")
def research(ctx: StageContext) -> StageResult:
    title = ctx.video.get("title") or ctx.video["video_id"]
    claims = [
        {"id": f"c{i:02d}", "text": f"claim {i} about {title}", "source": "closed_corpus", "confidence": 0.9}
        for i in range(1, 4)
    ]
    return StageResult.from_json(
        {"video_id": ctx.video["video_id"], "locale": ctx.config.get("locale"), "claims": claims},
        cost_usd=0.0, model_version=ctx.model_version,
    )


@handler(G, "script")
def script(ctx: StageContext) -> StageResult:
    research_doc = ctx.inp("research").json()
    assert ctx.beat is not None
    brief = ctx.beat.inputs.get("text", "")
    narration = f"[{ctx.beat.beat_id}] {brief} (grounded in {len(research_doc['claims'])} claims)"
    return StageResult.from_json(
        {
            "id": ctx.beat.beat_id,
            "ordinal": ctx.beat.ordinal,
            "narration": narration,
            "claims": [c["id"] for c in research_doc["claims"][:2]],
            "audience_level": ctx.config.get("audience_level"),
            # load budget per §11.2 — a real handler computes this, the fake one
            # keeps the shape so downstream code can be written against it now
            "load": {"new_symbols": 0, "new_terms": 1, "new_relationships": 1, "score": 2},
        },
        cost_usd=0.0, model_version=ctx.model_version,
    )


def _silent_wav(n_samples: int, rate: int = 16000) -> bytes:
    """Minimal valid mono 16-bit WAV. Deterministic for a given sample count."""
    data = b"\x00\x00" * n_samples
    hdr = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt "
    hdr += struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
    hdr += b"data" + struct.pack("<I", len(data))
    return hdr + data


@handler(G, "tts")
def tts(ctx: StageContext) -> StageResult:
    narration = ctx.inp("script").json()["narration"]
    # ~13 chars/second of speech — good enough to make durations vary with text
    ms = max(500, int(len(narration) / 13 * 1000))
    return StageResult(
        data=_silent_wav(int(16000 * ms / 1000)),
        mime="audio/wav",
        duration_ms=ms,
        cost_usd=0.0,
        model_version=ctx.model_version,
        meta={"chars": len(narration)},
    )


@handler(G, "pacing")
def pacing(ctx: StageContext) -> StageResult:
    """Code, not a model (§9.6). Reads its own beat plus both neighbours."""
    assert ctx.beat is not None
    self_wav = ctx.inp("tts:self")
    neighbours = {
        label.split(":")[1]: len(inp.data)
        for label, inp in sorted(ctx.inputs.items())
        if label.startswith("tts:") and label != "tts:self"
    }
    dur_ms = int((len(self_wav.data) - 44) / 2 / 16000 * 1000)
    lead_in_ms = 120 if "prev1" in neighbours else 400   # cold open gets more air
    tail_ms = 180 if "next1" in neighbours else 600
    return StageResult.from_json(
        {
            "beat_id": ctx.beat.beat_id,
            "ordinal": ctx.beat.ordinal,
            "narration_ms": dur_ms,
            "lead_in_ms": lead_in_ms,
            "tail_ms": tail_ms,
            "total_ms": dur_ms + lead_in_ms + tail_ms,
            "neighbours": sorted(neighbours),
        }
    )


@handler(G, "assembly")
def assembly(ctx: StageContext) -> StageResult:
    beats = [i.json() for i in ctx.inputs_like("pacing:")]
    beats.sort(key=lambda b: b["ordinal"])
    total = sum(b["total_ms"] for b in beats)
    return StageResult.from_json(
        {
            "video_id": ctx.video["video_id"],
            "beat_count": len(beats),
            "runtime_ms": total,
            "timeline": [{"beat_id": b["beat_id"], "ms": b["total_ms"]} for b in beats],
            # global-scope by nature (§5.5)
            "loudness_lufs": -14.0,
            "true_peak_dbtp": -1.0,
        }
    )

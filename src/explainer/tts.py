"""Text to speech — §6 Stage 4, CHALLENGES R5, §16.1.

One call per scene, not per span. Spans are an authoring and anchoring
construct (R4); synthesising them separately would put a glottal reset and a
prosody boundary at every span edge, which is audible and wrong. The spans are
recovered afterwards from the alignment (`align.py`), which is the direction
§16.1 prescribes: *"take TTS-native timestamps first"*.

## R5 — duration is derived, never authored

Nothing here reads `duration_target_seconds`. The slot budget is a budget; what
comes out of TTS is the truth, and where the two disagree the linter reports it
(ISSUE-9) rather than the synthesiser trimming words to fit.

## The closure (invariant 1)

    text after lexicon · voice id · model id · sample rate ·
    synthesis params · lexicon version · resampler version

and **nothing else**. No scene ref, no video id, no run id, no timestamp. Two
scenes anywhere in the corpus with identical narration and voice share one WAV
and one synthesis — which is a real slice of §6.3's cost curve, and the reason
`video_id` must never leak in here.

## Determinism, and the price paid for it

MEASURED: piper's default configuration is **not** reproducible. Two synthesis
calls on the same text produced audio of different LENGTHS (120832 vs 125952
samples), differing from sample zero. That is VITS's stochastic sampling —
`noise_scale` on the flow and `noise_w_scale` on the duration predictor — not
floating-point drift, and seeding numpy does not reach it.

Setting both to zero makes output byte-identical across runs and across fresh
processes. §11.3 requires exactly this, and it lists `Math.random()` first for
the same reason. The price is slightly flatter prosody, and it is worth paying:
a cache that returns different bytes for the same key is not a cache, and §11.3
calls a corrupted cache a bug that "will otherwise take weeks to diagnose".

`SYNTHESIS_PARAMS` is therefore part of the closure. Changing a value there
re-synthesises the corpus, which is correct — it is a different voice.
"""
from __future__ import annotations

import io
import json
import re
import subprocess
import wave
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from . import hashing, rtime
from .config import settings
from .store import store

STAGE = "tts"

# Piper's native rate for this voice. Resampled to rtime.SAMPLE_RATE before
# anything downstream sees it, because §11.4's 1600-samples-per-frame identity
# only holds at 48 kHz.
PIPER_SAMPLE_RATE = 22050

# Zero noise = reproducible. See the module docstring; this is a measurement,
# not a preference.
SYNTHESIS_PARAMS = {"noise_scale": 0.0, "noise_w_scale": 0.0, "length_scale": 1.0}

VOICE_DIR = Path("var/voices")
LEXICON_DIR = Path("lexicons")


class TTSError(RuntimeError):
    pass


# ------------------------------------------------------------------ lexicon

@dataclass(frozen=True)
class Lexicon:
    version: str
    entries: tuple[tuple[str, str], ...] = ()

    def apply(self, text: str) -> str:
        """Whole-word, case-insensitive, longest-first.

        Longest-first matters: without it `SELECT FOR UPDATE` would be eaten by
        a shorter entry and the multi-word pronunciation would never fire.
        """
        out = text
        for term, say in self.entries:
            out = re.sub(rf"\b{re.escape(term)}\b", say, out, flags=re.IGNORECASE)
        return out


@lru_cache(maxsize=8)
def load_lexicon(name: str) -> Lexicon:
    path = LEXICON_DIR / f"{name}.json"
    if not path.exists():
        raise TTSError(
            f"lexicon '{name}' not found at {path}. TTS_LEXICON is pinned in "
            f"config and the file must exist — an absent lexicon would change "
            f"pronunciation silently.")
    doc = json.loads(path.read_text(encoding="utf-8"))
    pairs = [(e["term"], e["say"]) for e in doc.get("entries", [])]
    pairs.sort(key=lambda p: -len(p[0]))
    return Lexicon(version=name, entries=tuple(pairs))


# ------------------------------------------------------------------- result

@dataclass
class SceneAudio:
    """One scene's synthesised narration, content-addressed."""

    hash: str
    sample_rate: int
    sample_count: int
    # Per-phoneme spans in samples at `sample_rate`, in emission order.
    phonemes: list[dict] = field(default_factory=list)
    # One entry per synthesis chunk: piper emits exactly one chunk per
    # sentence, and `Narration.author` segments on the same boundaries, so
    # these are span durations MEASURED rather than estimated. `align.py`
    # checks the counts match and refuses to guess when they do not.
    chunks: list[dict] = field(default_factory=list)
    cached: bool = False
    voice: str = ""
    model: str = ""
    lexicon: str = ""

    @property
    def duration(self) -> rtime.RationalTime:
        """R5: derived from the audio, never authored."""
        return rtime.RationalTime.from_samples(self.sample_count,
                                               self.sample_rate)

    @property
    def seconds(self) -> float:
        return self.sample_count / self.sample_rate


# -------------------------------------------------------------------- voice

@lru_cache(maxsize=4)
def _voice(voice_id: str):
    try:
        from piper import PiperVoice
    except ImportError as e:  # pragma: no cover - environment problem
        raise TTSError(
            "piper-tts is not installed. `pip install piper-tts`, then "
            "`python -m piper.download_voices <voice> --data-dir var/voices`."
        ) from e
    path = VOICE_DIR / f"{voice_id}.onnx"
    if not path.exists():
        raise TTSError(
            f"voice '{voice_id}' not found at {path}. It is pinned in config "
            f"(TTS_VOICE) and must be present: falling back to another voice "
            f"would change every hash in the corpus.")
    return PiperVoice.load(str(path))


def voice_fingerprint(voice_id: str) -> str:
    """Content hash of the voice model itself.

    In the closure because a voice file swapped underneath the same NAME is a
    different voice, and pinning the name alone would serve stale audio.
    """
    path = VOICE_DIR / f"{voice_id}.onnx"
    if not path.exists():
        raise TTSError(f"voice '{voice_id}' not found at {path}")
    return _file_hash(path)


@lru_cache(maxsize=8)
def _file_hash(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# ---------------------------------------------------------------- resampler

@lru_cache(maxsize=1)
def ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return "ffmpeg"


@lru_cache(maxsize=1)
def ffmpeg_version() -> str:
    """§11.3: 'Chromium / FFmpeg / codec versions -> part of the cache key.'"""
    out = subprocess.run([ffmpeg_exe(), "-version"], capture_output=True,
                         text=True, check=True).stdout
    return out.splitlines()[0].strip()


def _resample(pcm: bytes, from_rate: int, to_rate: int) -> bytes:
    """Mono s16 PCM -> mono s16 PCM at `to_rate`, via a pinned soxr path.

    Every swr parameter is stated explicitly rather than left to ffmpeg's
    defaults, because those defaults have changed between releases and a
    resampler change would silently alter every audio hash in the corpus.

    MEASURED: `resampler=soxr` is not available in the imageio-ffmpeg 7.1 build
    ("Requested resampling engine is unavailable"), so swr is used with pinned
    filter_size/phase_shift/cutoff. Which engine matters far less than the
    parameters being fixed; the engine name is in `ffmpeg_version()`, which is
    in the closure, so a build that gains soxr does not silently change output.
    """
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
           "-f", "s16le", "-ar", str(from_rate), "-ac", "1", "-i", "pipe:0",
           "-af", (f"aresample=resampler=swr:osr={to_rate}"
                   f":filter_size=32:phase_shift=10:cutoff=0.97"
                   f":dither_method=0"),
           "-f", "s16le", "-ac", "1", "-ar", str(to_rate), "pipe:1"]
    p = subprocess.run(cmd, input=pcm, capture_output=True)
    if p.returncode != 0:
        raise TTSError(f"resample failed: {p.stderr.decode(errors='replace')[:500]}")
    return p.stdout


# ------------------------------------------------------------------ synthesis

def closure(text: str, *, voice_id: str, model_id: str, lexicon: Lexicon) -> str:
    """Invariant 1: inputs only. No scene ref, no video id, no timestamp."""
    return hashing.closure_hash(
        kind=STAGE,
        upstream={},
        prompt_version=None,
        model_version=model_id,
        code_version=None,
        config={"voice": voice_id,
                "voice_sha": voice_fingerprint(voice_id),
                "sample_rate": rtime.SAMPLE_RATE,
                "lexicon": lexicon.version,
                "resampler": ffmpeg_version()},
        extra={"text": text, "params": SYNTHESIS_PARAMS})


def synthesize_spans(texts: list[str], **kw) -> "SceneAudio":
    """Fallback: synthesise each span separately and concatenate.

    Used ONLY when per-scene synthesis produces a chunk partition that does not
    match the span partition (see ISSUE-11). Per-scene is the primary path and
    stays that way: it is one call, and it lets piper carry prosody across a
    sentence boundary the way a reader would.

    Acoustically this is close to the per-scene path for correctly segmented
    text, because piper already resets prosody per sentence internally. Where a
    span is NOT a sentence — which is exactly the ISSUE-11 case — the reset is
    audible, and that is deliberate: it makes the segmentation defect something
    you can hear rather than something buried in a hash.
    """
    parts = [synthesize(t, **kw) for t in texts]
    pcm = b"".join(read_pcm(p.hash) for p in parts)
    chunks, cursor = [], 0
    for p in parts:
        chunks.append({"start": cursor, "end": cursor + p.sample_count,
                       "phonemes": ""})
        cursor += p.sample_count

    st = store()
    h = hashing.sha256_hex(hashing.canonical_json(
        {"concat": [p.hash for p in parts]}))
    meta_hash = h[:60] + "meta"
    if not st.exists(h):
        st.put(h, _wav_bytes(pcm, rtime.SAMPLE_RATE), mime="audio/wav")
        st.put_json(meta_hash, {"sample_count": cursor, "phonemes": [],
                                "chunks": chunks, "voice": parts[0].voice,
                                "model": parts[0].model,
                                "lexicon": parts[0].lexicon,
                                "per_span_fallback": True,
                                "parts": [p.hash for p in parts]})
    return SceneAudio(hash=h, sample_rate=rtime.SAMPLE_RATE,
                      sample_count=cursor, chunks=chunks,
                      cached=all(p.cached for p in parts),
                      voice=parts[0].voice, model=parts[0].model,
                      lexicon=parts[0].lexicon)


def synthesize(text: str, *, voice_id: str | None = None,
               model_id: str | None = None,
               lexicon_name: str | None = None) -> SceneAudio:
    """Synthesise one scene's narration. Cache hit returns without calling TTS."""
    s = settings()
    voice_id = voice_id or s.models.tts_voice
    model_id = model_id or s.models.tts_model
    if "unpinned" in (voice_id, model_id) or "latest" in f"{voice_id}{model_id}":
        raise TTSError(
            f"TTS voice/model must be pinned (invariant 6), got "
            f"voice={voice_id!r} model={model_id!r}. Set TTS_VOICE and "
            f"TTS_MODEL in config.")
    lex = load_lexicon(lexicon_name or getattr(s.models, "tts_lexicon", "en.v1"))
    spoken = lex.apply(text)

    h = closure(spoken, voice_id=voice_id, model_id=model_id, lexicon=lex)
    st = store()
    meta_hash = h[:60] + "meta"          # sidecar for the alignment payload

    if st.exists(h) and st.exists(meta_hash):
        meta = st.get_json(meta_hash)
        return SceneAudio(hash=h, sample_rate=rtime.SAMPLE_RATE,
                          sample_count=meta["sample_count"],
                          phonemes=meta.get("phonemes") or [],
                          chunks=meta.get("chunks") or [], cached=True,
                          voice=voice_id, model=model_id, lexicon=lex.version)

    from piper import SynthesisConfig
    v = _voice(voice_id)
    cfg = SynthesisConfig(**SYNTHESIS_PARAMS)

    pcm = bytearray()
    phonemes: list[dict] = []
    chunks: list[dict] = []
    for chunk in v.synthesize(spoken, syn_config=cfg):
        audio = chunk.audio_int16_bytes
        start = len(pcm) // 2
        pcm += audio
        end = len(pcm) // 2
        chunks.append({"start": start, "end": end,
                       "phonemes": "".join(chunk.phonemes or [])})
        # phoneme_id_samples is empty for voices that do not export alignment
        # outputs, which is the case for en_US-lessac-medium. Kept because a
        # voice that DOES export them makes word timing measured rather than
        # estimated, and the code should not need changing when one arrives.
        cursor = start
        for ph, n in zip(chunk.phonemes or [],
                         getattr(chunk, "phoneme_id_samples", None) or []):
            phonemes.append({"phoneme": ph, "start": cursor,
                             "end": cursor + int(n)})
            cursor += int(n)

    if not pcm:
        raise TTSError(f"TTS produced no audio for {text[:80]!r}")

    pcm48 = _resample(bytes(pcm), PIPER_SAMPLE_RATE, rtime.SAMPLE_RATE)
    scale = rtime.SAMPLE_RATE / PIPER_SAMPLE_RATE
    total48 = len(pcm48) // 2
    for p in phonemes:
        p["start"] = int(round(p["start"] * scale))
        p["end"] = int(round(p["end"] * scale))
    for i, c in enumerate(chunks):
        c["start"] = int(round(c["start"] * scale))
        c["end"] = int(round(c["end"] * scale))
    # The last chunk absorbs any rounding remainder so the chunks tile the
    # audio exactly: a one-sample gap here becomes a drift the timing resolver
    # would have to invent a rule to absorb.
    if chunks:
        chunks[0]["start"] = 0
        for a, b in zip(chunks, chunks[1:]):
            b["start"] = a["end"]
        chunks[-1]["end"] = total48

    wav = _wav_bytes(pcm48, rtime.SAMPLE_RATE)
    st.put(h, wav, mime="audio/wav")
    sample_count = len(pcm48) // 2
    st.put_json(meta_hash, {"sample_count": sample_count, "phonemes": phonemes,
                            "chunks": chunks, "voice": voice_id,
                            "model": model_id, "lexicon": lex.version,
                            "spoken_text": spoken})
    return SceneAudio(hash=h, sample_rate=rtime.SAMPLE_RATE,
                      sample_count=sample_count, phonemes=phonemes,
                      chunks=chunks, cached=False, voice=voice_id,
                      model=model_id, lexicon=lex.version)


def _wav_bytes(pcm: bytes, rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def read_pcm(hash_: str) -> bytes:
    """The raw mono s16 samples behind a stored WAV."""
    with wave.open(io.BytesIO(store().get(hash_)), "rb") as w:
        if w.getframerate() != rtime.SAMPLE_RATE or w.getnchannels() != 1:
            raise TTSError(
                f"stored audio {hash_[:12]} is "
                f"{w.getframerate()}Hz/{w.getnchannels()}ch; the pipeline is "
                f"pinned to {rtime.SAMPLE_RATE}Hz mono")
        return w.readframes(w.getnframes())

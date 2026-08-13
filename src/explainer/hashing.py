"""Content addressing (PRD §5.2).

    hash(artifact) = H(
        [hashes of all upstream input artifacts]
      + prompt_template_version
      + model_id + model_version
      + code_version
      + config (voice_id, brand_version, locale, audience_level)
    )

Non-canonical serialization is the classic source of phantom cache misses, so
canonicalization is strict and tested (tests/test_hashing.py):

  * keys sorted, no whitespace, UTF-8, no ensure_ascii escaping
  * NaN / Infinity rejected outright (they round-trip inconsistently)
  * floats emitted with repr() — shortest round-trippable form
  * ints and floats are distinct: 1 and 1.0 hash differently, on purpose
  * None is serialized as null; a missing key and an explicit null are the
    SAME thing here, because a stage that omits an optional field and one that
    sets it to null produce identical output

DO NOT put video_id, series_id, timestamps, run ids or worker ids into a
closure. Two videos that legitimately produce the same title card must land on
the same hash — that is where a real slice of the S5 cost curve comes from.
"""
from __future__ import annotations

import hashlib
import math
from typing import Any

HASH_ALGO = "sha256"
CLOSURE_SCHEMA_VERSION = 1  # bump only for a deliberate global cache flush


def _canon(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError("NaN/Infinity cannot be hashed canonically")
        return {"__f__": repr(value)}
    if isinstance(value, dict):
        out = {}
        for k in sorted(value.keys()):
            if not isinstance(k, str):
                raise TypeError(f"non-string dict key in closure: {k!r}")
            out[k] = _canon(value[k])
        return out
    if isinstance(value, (list, tuple)):
        return [_canon(v) for v in value]
    if isinstance(value, (set, frozenset)):
        raise TypeError("sets are unordered and must not appear in a closure")
    if isinstance(value, bytes):
        return {"__b__": hashlib.sha256(value).hexdigest()}
    raise TypeError(f"unhashable type in closure: {type(value).__name__}")


def canonical_json(value: Any) -> bytes:
    import json

    return json.dumps(
        _canon(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def content_hash(data: bytes) -> str:
    """Hash of a blob's bytes. Used for integrity checks only — never as a key."""
    return sha256_hex(data)


def closure_hash(
    *,
    kind: str,
    upstream: dict[str, str],
    prompt_version: str | None,
    model_version: str | None,
    code_version: str | None,
    config: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    """Compute an artifact hash from its full input closure.

    `upstream` maps a dependency label -> upstream artifact hash. Labels are part
    of the closure so swapping two inputs of the same stage changes the hash.

    `extra` carries stage-local inputs that are not artifacts (e.g. the beat
    brief the human typed). Put anything that legitimately changes the output
    here; put nothing else.
    """
    closure = {
        "v": CLOSURE_SCHEMA_VERSION,
        "kind": kind,
        "upstream": {k: upstream[k] for k in sorted(upstream)},
        "prompt_version": prompt_version,
        "model_version": model_version,
        "code_version": code_version,
        "config": config or {},
        "extra": extra or {},
    }
    return sha256_hex(canonical_json(closure))

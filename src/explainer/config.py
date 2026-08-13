"""Configuration. Every value that can change an artifact's identity lives here
and is fed into the hash closure (§5.2).

Model IDs are PINNED. Never 'latest' — see PRD §6.6.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")


def _env(key: str, default: str | None = None) -> str:
    v = os.getenv(key, default)
    if v is None:
        raise RuntimeError(f"missing required env var: {key}")
    return v


@dataclass(frozen=True)
class ModelPins:
    """Pinned model ids per tier (PRD §7 build-vs-buy, §9.6 roster tiers).

    These strings go into the hash closure. Changing one is a deliberate
    migration that triggers a golden-set regression run (§14.4).
    """

    frontier: str = field(default_factory=lambda: _env("MODEL_FRONTIER", "claude-opus-4-6-20260401"))
    mid: str = field(default_factory=lambda: _env("MODEL_MID", "claude-sonnet-4-6-20260315"))
    vision: str = field(default_factory=lambda: _env("MODEL_VISION", "claude-sonnet-4-6-20260315"))
    tts_voice: str = field(default_factory=lambda: _env("TTS_VOICE", "unpinned"))
    tts_model: str = field(default_factory=lambda: _env("TTS_MODEL", "unpinned"))

    def for_tier(self, tier: str) -> str:
        return {
            "frontier": self.frontier,
            "mid": self.mid,
            "vision": self.vision,
            "code": "code",  # deterministic stages: pacing, assembly (§9.6)
            "tts": f"{self.tts_model}/{self.tts_voice}",
        }[tier]


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: _env(
        "DATABASE_URL", "postgresql://dev:dev@localhost:5432/explainer"))

    # Artifact store: 'local' for dev, 's3' for S3 / R2 / Supabase Storage.
    artifact_backend: str = field(default_factory=lambda: _env("ARTIFACT_BACKEND", "local"))
    artifact_local_dir: Path = field(default_factory=lambda: Path(
        _env("ARTIFACT_LOCAL_DIR", str(REPO_ROOT / ".artifacts"))))
    s3_bucket: str = field(default_factory=lambda: os.getenv("S3_BUCKET", ""))
    s3_endpoint: str = field(default_factory=lambda: os.getenv("S3_ENDPOINT", ""))
    s3_region: str = field(default_factory=lambda: os.getenv("S3_REGION", "auto"))
    s3_prefix: str = field(default_factory=lambda: os.getenv("S3_PREFIX", "artifacts"))

    # Worker
    worker_pools: tuple[str, ...] = field(default_factory=lambda: tuple(
        p.strip() for p in _env("WORKER_POOLS", "agent,render,media").split(",") if p.strip()))
    heartbeat_interval_s: int = field(default_factory=lambda: int(_env("HEARTBEAT_INTERVAL_S", "15")))
    heartbeat_timeout_s: int = field(default_factory=lambda: int(_env("HEARTBEAT_TIMEOUT_S", "120")))

    # Guardrail from §6.7 — a runaway loop against a frontier model is a real
    # and boring way to lose money.
    series_cost_cap_usd: float = field(default_factory=lambda: float(_env("SERIES_COST_CAP_USD", "250")))

    env: str = field(default_factory=lambda: _env("APP_ENV", "local"))
    models: ModelPins = field(default_factory=ModelPins)

    def hashable_config(self) -> dict:
        """Only values that legitimately change output identity.

        Deliberately EXCLUDES database_url, storage location, worker settings and
        cost caps — those are deployment details, not inputs. Including them
        would fork the cache per environment and destroy cross-video dedupe.
        """
        return {
            "models": {
                "frontier": self.models.frontier,
                "mid": self.models.mid,
                "vision": self.models.vision,
                "tts_model": self.models.tts_model,
                "tts_voice": self.models.tts_voice,
            }
        }


_settings: Settings | None = None


def settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings

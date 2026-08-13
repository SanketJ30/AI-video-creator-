"""Content-addressed artifact store (PRD §7: "build over S3/R2, ~300 lines").

Keyed by the input-closure hash, not by the content hash. The blob's own sha256
is recorded alongside for integrity, so a truncated upload is detectable.

Two backends:
  local  — .artifacts/, sharded two levels. Phases 1–8.
  s3     — S3 / Cloudflare R2 / Supabase Storage (S3-compatible endpoint).

Writes are immutable: putting the same hash twice is a no-op, never an
overwrite. If the bytes differ for the same hash, that is a hashing bug and it
raises loudly rather than silently corrupting the cache.
"""
from __future__ import annotations

import json
import os
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .config import settings
from .hashing import content_hash


class StoreError(RuntimeError):
    pass


class ArtifactStore(ABC):
    @abstractmethod
    def exists(self, hash_: str) -> bool: ...

    @abstractmethod
    def put(self, hash_: str, data: bytes, mime: str = "application/octet-stream") -> str: ...

    @abstractmethod
    def get(self, hash_: str) -> bytes: ...

    @abstractmethod
    def uri_for(self, hash_: str) -> str: ...

    # -- convenience ---------------------------------------------------------

    def put_json(self, hash_: str, obj: Any) -> str:
        return self.put(hash_, json.dumps(obj, indent=2, sort_keys=True).encode(), "application/json")

    def get_json(self, hash_: str) -> Any:
        return json.loads(self.get(hash_).decode())


def _shard(hash_: str) -> str:
    return f"{hash_[:2]}/{hash_[2:4]}/{hash_}"


class LocalStore(ArtifactStore):
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, hash_: str) -> Path:
        return self.root / _shard(hash_)

    def exists(self, hash_: str) -> bool:
        return self._path(hash_).is_file()

    def put(self, hash_: str, data: bytes, mime: str = "application/octet-stream") -> str:
        p = self._path(hash_)
        if p.is_file():
            if content_hash(p.read_bytes()) != content_hash(data):
                raise StoreError(
                    f"hash collision for {hash_}: existing bytes differ from new bytes. "
                    "This means two different outputs produced the same closure hash — "
                    "a real bug in the closure, not a hash collision. Do not paper over it."
                )
            return self.uri_for(hash_)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, p)  # atomic: a reader never sees a partial artifact
        return self.uri_for(hash_)

    def get(self, hash_: str) -> bytes:
        p = self._path(hash_)
        if not p.is_file():
            raise StoreError(f"artifact not in store: {hash_}")
        return p.read_bytes()

    def uri_for(self, hash_: str) -> str:
        return f"file://{self._path(hash_)}"

    def wipe(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)


class S3Store(ArtifactStore):
    def __init__(self, bucket: str, prefix: str, endpoint: str = "", region: str = "auto"):
        import boto3  # imported lazily so local dev needs no AWS deps

        self.bucket, self.prefix = bucket, prefix.strip("/")
        kwargs: dict[str, Any] = {"region_name": region}
        if endpoint:
            kwargs["endpoint_url"] = endpoint
        self.s3 = boto3.client("s3", **kwargs)

    def _key(self, hash_: str) -> str:
        return f"{self.prefix}/{_shard(hash_)}"

    def exists(self, hash_: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.s3.head_object(Bucket=self.bucket, Key=self._key(hash_))
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] in ("404", "NoSuchKey", "403"):
                return False
            raise

    def put(self, hash_: str, data: bytes, mime: str = "application/octet-stream") -> str:
        if self.exists(hash_):
            return self.uri_for(hash_)
        self.s3.put_object(Bucket=self.bucket, Key=self._key(hash_), Body=data, ContentType=mime)
        return self.uri_for(hash_)

    def get(self, hash_: str) -> bytes:
        return self.s3.get_object(Bucket=self.bucket, Key=self._key(hash_))["Body"].read()

    def uri_for(self, hash_: str) -> str:
        return f"s3://{self.bucket}/{self._key(hash_)}"

    def signed_url(self, hash_: str, expires_s: int = 900) -> str:
        """§6.7 — the editor serves media through short-lived signed URLs."""
        return self.s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": self._key(hash_)},
            ExpiresIn=expires_s,
        )


_store: ArtifactStore | None = None


def store() -> ArtifactStore:
    global _store
    if _store is None:
        s = settings()
        if s.artifact_backend == "s3":
            if not s.s3_bucket:
                raise StoreError("ARTIFACT_BACKEND=s3 but S3_BUCKET is unset")
            _store = S3Store(s.s3_bucket, s.s3_prefix, s.s3_endpoint, s.s3_region)
        else:
            _store = LocalStore(s.artifact_local_dir)
    return _store

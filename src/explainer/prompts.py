"""Prompt version registry (PRD §6.6).

    "Prompts are code. They live in git under prompts/, are reviewed in PRs, and
     are versioned. There is no prompt-editing UI in v1 — the moment prompts
     become editable at runtime, the artifact hash lies and regression testing
     becomes meaningless."

Files are named `prompts/<name>.v<N>.md`. The version string that enters the
hash closure is `<name>@v<N>+<body_sha8>`. The body hash is there deliberately:
bumping the filename is the reviewed, intentional act, but an unbumped edit
still invalidates downstream artifacts rather than silently serving stale ones.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from .config import REPO_ROOT
from .hashing import sha256_hex

PROMPT_DIR = REPO_ROOT / "prompts"
_PATTERN = re.compile(r"^(?P<name>[a-z0-9_]+)\.v(?P<ver>\d+)\.md$")


class PromptMissing(RuntimeError):
    pass


@dataclass(frozen=True)
class PromptRef:
    name: str
    file_version: int
    body: str
    body_sha: str

    @property
    def version(self) -> str:
        return f"{self.name}@v{self.file_version}+{self.body_sha[:8]}"


@lru_cache(maxsize=128)
def load(name: str) -> PromptRef:
    """Load the highest-numbered version of a prompt."""
    candidates: list[tuple[int, "object"]] = []
    if PROMPT_DIR.is_dir():
        for f in PROMPT_DIR.iterdir():
            m = _PATTERN.match(f.name)
            if m and m.group("name") == name:
                candidates.append((int(m.group("ver")), f))
    if not candidates:
        raise PromptMissing(
            f"no prompt file for '{name}'. Create prompts/{name}.v1.md — "
            "prompts are code, so it must be committed, not typed at runtime."
        )
    ver, path = max(candidates, key=lambda c: c[0])
    body = path.read_text()  # type: ignore[union-attr]
    return PromptRef(name=name, file_version=ver, body=body, body_sha=sha256_hex(body.encode()))


def register(conn, ref: PromptRef, git_sha: str | None = None) -> None:
    """Record a prompt version the first time it is used. Append-only."""
    with conn.cursor() as cur:
        cur.execute(
            """insert into prompt_versions(name, version, body, body_sha, git_sha)
               values (%s, %s, %s, %s, %s)
               on conflict (name, version, body_sha) do nothing""",
            (ref.name, f"v{ref.file_version}", ref.body, ref.body_sha, git_sha),
        )


def all_prompts() -> list[PromptRef]:
    names = set()
    if PROMPT_DIR.is_dir():
        for f in PROMPT_DIR.iterdir():
            m = _PATTERN.match(f.name)
            if m:
                names.add(m.group("name"))
    return [load(n) for n in sorted(names)]

"""code_version resolution (PRD §5.2).

    "code_version is the git SHA of the template/renderer directory, not of the
     whole repo. Otherwise every unrelated commit invalidates every render."

So this resolves a *tree* SHA for one subdirectory. Two extra rules that matter
in practice:

  * If the directory has uncommitted changes, we fall back to a content hash
    prefixed `dirty-`. Using the last commit's tree SHA while you are editing a
    template is the fastest way to get a phantom cache hit and spend an
    afternoon wondering why your change did nothing.
  * Results are memoised per process, so a worker that runs 40 jobs shells out
    to git once per directory, not 40 times.
"""
from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path

from .config import REPO_ROOT
from .hashing import sha256_hex

# Which directory's code owns each stage's output. Adding a stage means adding a
# row here — otherwise its code changes will not invalidate anything.
STAGE_CODE_DIRS: dict[str, str] = {
    "*": "src/explainer/stages",
    "render": "remotion",
    "pacing": "src/explainer/stages",
    "assembly": "src/explainer/stages",
    "sound_design": "src/explainer/stages",
}


def _run(args: list[str], cwd: Path) -> tuple[int, str]:
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    return p.returncode, (p.stdout or "").strip()


def _content_hash_dir(path: Path) -> str:
    parts: list[str] = []
    if path.is_dir():
        for f in sorted(path.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts and "node_modules" not in f.parts:
                parts.append(str(f.relative_to(path)))
                parts.append(sha256_hex(f.read_bytes()))
    return sha256_hex("\n".join(parts).encode())[:16]


@lru_cache(maxsize=64)
def code_version_for_dir(rel: str) -> str:
    path = REPO_ROOT / rel
    if not path.exists():
        return "absent"
    rc, dirty = _run(["git", "status", "--porcelain", "--", rel], REPO_ROOT)
    if rc != 0:
        return f"nogit-{_content_hash_dir(path)}"
    if dirty:
        return f"dirty-{_content_hash_dir(path)}"
    rc, tree = _run(["git", "rev-parse", f"HEAD:{rel}"], REPO_ROOT)
    if rc != 0 or not tree:
        return f"untracked-{_content_hash_dir(path)}"
    return tree[:16]


def code_version_for_stage(stage: str) -> str:
    rel = STAGE_CODE_DIRS.get(stage, STAGE_CODE_DIRS["*"])
    return code_version_for_dir(rel)

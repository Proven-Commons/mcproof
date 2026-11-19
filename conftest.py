"""Root pytest configuration wiring unified repo and sibling siliconcordat packages into sys.path."""

from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent
LAB_ROOT = REPO_ROOT.parent
SILICONCORDAT_ROOT = LAB_ROOT.parent / "siliconcordat"
WORKTREES_ROOT = LAB_ROOT / "stack" / "worktrees"

CANDIDATE_PATHS = (
    REPO_ROOT / "src",
    REPO_ROOT / "tests",
    REPO_ROOT / "compile" / "src",
    REPO_ROOT / "stack" / "src",
    WORKTREES_ROOT / "warp" / "src",
    WORKTREES_ROOT / "exo" / "src",
    SILICONCORDAT_ROOT / "warp" / "src",
    SILICONCORDAT_ROOT / "exo" / "src",
    SILICONCORDAT_ROOT / "weft" / "src",
)

for cand in reversed(CANDIDATE_PATHS):
    if cand.is_dir():
        cand_str = str(cand.resolve())
        if cand_str not in sys.path:
            sys.path.insert(0, cand_str)

"""Root pytest configuration wiring unified repo and sibling siliconcordat packages into sys.path."""

from __future__ import annotations

import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent
LAB_ROOT = REPO_ROOT.parent
_SC_ENV = os.environ.get("MCPROOF_SILICONCORDAT_DIR")
SILICONCORDAT_DIRS = (
    (Path(_SC_ENV).expanduser(),)
    if _SC_ENV is not None
    else (LAB_ROOT / "siliconcordat", LAB_ROOT.parent / "siliconcordat")
)
WORKTREES_ROOT = LAB_ROOT / "stack" / "worktrees"

CANDIDATE_PATHS = [
    REPO_ROOT / "src",
    REPO_ROOT / "tests",
    REPO_ROOT / "compile" / "src",
    REPO_ROOT / "stack" / "src",
]
if _SC_ENV is None:
    CANDIDATE_PATHS.extend(
        [
            WORKTREES_ROOT / "warp" / "src",
            WORKTREES_ROOT / "exo" / "src",
        ]
    )
for _sc_root in SILICONCORDAT_DIRS:
    CANDIDATE_PATHS.extend(
        [
            _sc_root / "warp" / "src",
            _sc_root / "exo" / "src",
            _sc_root / "weft" / "src",
        ]
    )

for cand in reversed(CANDIDATE_PATHS):
    if cand.is_dir():
        cand_str = str(cand.resolve())
        if cand_str not in sys.path:
            sys.path.insert(0, cand_str)

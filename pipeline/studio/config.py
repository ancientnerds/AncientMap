"""Where the studio keeps its working files, resolved from the main checkout.

STUDIO_ASSETS defaults to `<main checkout>/video-assets/studio`. The main checkout is the
parent of git's common dir, so a session running in a worktree (AncientMap-studio) still
writes into the one gitignored asset tree of C:/PythonProjects/AncientMap, where the fonts,
the music bed and the local .env live. The env var STUDIO_ASSETS overrides it (tests use it).

This module is also the one home of the studio's shared patterns (a request id, a sha256, a
capture id and the capture kinds): casefile.py, script.py, ledger.py and stream D's
capture/manifest.py import them. Its module level stays standard library only, because
ledger.py runs inside the API container.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from pipeline.studio.errors import StudioError

REPO = Path(__file__).resolve().parents[2]

#: A research request id: a lowercase uuid, the paper workspace's directory name.
REQUEST_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
#: A sha256 hex digest (case file, script, video, paper).
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
#: A capture id (contract C7): it names the capture's media file under captures/.
CAPTURE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
#: The capture kinds of contract C7, one recorder each.
CAPTURE_KINDS = ("platform", "globe", "source", "mapbox_topdown")
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def main_checkout_from(common_dir: str) -> Path:
    """The main checkout for git's `--git-common-dir` answer (`<main>/.git`)."""
    path = Path(common_dir.strip())
    if path.name != ".git":
        raise StudioError(f"git common dir {common_dir!r} is not a '.git' directory")
    return path.parent


def main_checkout() -> Path:
    """The main checkout this code's repository belongs to (worktree-safe)."""
    command = ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"]
    where = f"cannot locate the main checkout: `{' '.join(command)}` in {REPO}"
    try:
        proc = subprocess.run(command, cwd=REPO, capture_output=True, text=True, timeout=30)
    except FileNotFoundError as exc:
        raise StudioError(f"{where}: git is not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise StudioError(f"{where} gave no answer within 30 s") from exc
    if proc.returncode != 0:
        raise StudioError(f"{where} exited {proc.returncode}: {proc.stderr.strip()[-400:]}")
    return main_checkout_from(proc.stdout)


def studio_assets() -> Path:
    """Root of the studio workspaces: $STUDIO_ASSETS, else <main>/video-assets/studio.

    Always absolute: a relative override is taken against the current directory here, once,
    because ffmpeg's concat lists and the node renderer (cwd video/) read workspace paths
    from other directories."""
    override = os.environ.get("STUDIO_ASSETS", "").strip()
    if override:
        return Path(override).absolute()
    return main_checkout() / "video-assets" / "studio"


def video_assets() -> Path:
    """The main checkout's video-assets/ (music bed, brand fonts, shorts)."""
    return main_checkout() / "video-assets"


def check_request_id(request_id: str) -> str:
    if not REQUEST_ID_RE.fullmatch(request_id):
        raise StudioError(f"{request_id!r} is not a research request id (lowercase uuid)")
    return request_id


def check_slug(slug: str) -> str:
    if not _SLUG_RE.fullmatch(slug):
        raise StudioError(f"{slug!r} is not a slug (lowercase letters, digits, single hyphens)")
    return slug


def paper_dir(request_id: str) -> Path:
    """The paper workspace `<STUDIO_ASSETS>/papers/<request_id>/`."""
    return studio_assets() / "papers" / check_request_id(request_id)


def episode_dir(slug: str) -> Path:
    """The episode workspace `<STUDIO_ASSETS>/episodes/<slug>/`."""
    return studio_assets() / "episodes" / check_slug(slug)


def load_env() -> None:
    """Load the main checkout's .env into os.environ (existing variables win).

    A worktree has no .env of its own; MiniMax (voice) and the connectors read their keys
    from the environment.
    """
    from dotenv import load_dotenv

    load_dotenv(main_checkout() / ".env", override=False)

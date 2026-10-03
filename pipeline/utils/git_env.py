# SPDX-License-Identifier: AGPL-3.0-only
"""Git that acts on the repository it was told to, whatever the shell exported.

`git -C <repo>` and `git` with `cwd=<repo>` are both overridden by an inherited `GIT_DIR`,
`GIT_WORK_TREE` or `GIT_INDEX_FILE`: git reads the repository from the environment before it
looks at the command line. On 2026-10-03 the pre-push hook exports `GIT_DIR` for the checkout
it pushes, and the test suite runs inside that hook, so every test that built a throwaway
repository - and every production call site that named one - was redirected into the branch
being pushed: a test's `commit -m a` landed on it, and the gate reported eight failures whose
`git` calls had answered about the wrong repository.

Every call that means a specific repository therefore runs in `own_env()`, and the plain
shape of that call is `run_git`. A caller that needs `check=True` or a timeout of its own
keeps its `subprocess.run` and passes `env=own_env()`.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def own_env() -> dict[str, str]:
    """This process's environment without any `GIT_*` variable.

    A caller that wants a `GIT_*` value of its own (a test that reads the gate's, say) sets it
    explicitly; a throwaway repository must not inherit one.
    """
    return {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}


def run_git(repo: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    """`git -C <repo> <argv>`, in an environment without `GIT_*`.

    A fixed set of keywords, so a caller cannot ask for a different decoding: git's output is
    always text, utf-8, and a failing command is a return code the caller inspects (the gates
    that print git's own message depend on it).
    """
    return subprocess.run(  # noqa: S603 - a fixed argv, `git` on PATH
        ["git", "-C", str(repo), *argv],  # noqa: S607 - git on PATH, as everywhere on the workstation
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        env=own_env(),
    )

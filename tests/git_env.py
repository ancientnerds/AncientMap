# SPDX-License-Identifier: AGPL-3.0-only
"""The environment a test's own `git` calls have to run in.

`.githooks/pre-push` exports `GIT_DIR` (and friends) so the gate's commands act on the
checkout that is being pushed. `GIT_DIR` wins over the directory a command runs in, so a
test that builds a throwaway repository with `git -C <tmp>` still writes into the pushed
repository: on 2026-10-03 a test's `commit -m a` landed on the branch mid-push, staged
`a.txt` in the real index and left the pre-push gate with 24 failures.

Every helper that calls git for a throwaway repository therefore passes `env=own_env()`.
"""

from __future__ import annotations

import os


def own_env() -> dict[str, str]:
    """This process's environment without any `GIT_*` variable.

    A test that wants the gate's `GIT_*` values for the real checkout reads them from
    `os.environ` itself; a throwaway repository must not inherit them.
    """
    return {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}

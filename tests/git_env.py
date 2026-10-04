# SPDX-License-Identifier: AGPL-3.0-only
"""The environment a test's own `git` calls have to run in.

`.githooks/pre-push` exports `GIT_DIR` (and friends) so the gate's commands act on the
checkout that is being pushed. `GIT_DIR` wins over the directory a command runs in, so a
test that builds a throwaway repository with `git -C <tmp>` still writes into the pushed
repository: on 2026-10-03 a test's `commit -m a` landed on the branch mid-push, staged
`a.txt` in the real index and left the pre-push gate with 24 failures.

Every helper that calls git for a throwaway repository therefore passes `env=own_env()`.
That helper is the production one - `pipeline.utils.git_env` is the single implementation,
because the production call sites that name a repository need exactly the same protection.
"""

from __future__ import annotations

from pipeline.utils.git_env import own_env

__all__ = ["own_env"]

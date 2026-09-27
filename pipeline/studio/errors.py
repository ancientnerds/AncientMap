"""The one exception type every studio step raises for a user-facing failure.

The CLI prints its message and exits 2. Anything else (a bug) propagates with its traceback.
"""

from __future__ import annotations


class StudioError(RuntimeError):
    """A studio step cannot go on; the message says exactly why and what to fix."""

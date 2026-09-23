# SPDX-License-Identifier: AGPL-3.0-only
"""Read a module-level function out of its source file, for tests that pin what the code calls.

Read as source on purpose: importing ``api.main`` builds the app and its routers, and a test about
which function a boot path calls must not depend on that.
"""

from __future__ import annotations

import ast
from pathlib import Path


def function_def(path: Path, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    """The module-level function ``name`` of ``path``, read from the source."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name
    ]
    assert len(found) == 1, f"{path} has no module-level function {name}"
    return found[0]


def names_used_by(path: Path, name: str) -> set[str]:
    """What the function calls by name, and what it imports as ``module.name``."""
    used: set[str] = set()
    for node in ast.walk(function_def(path, name)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            used.add(node.func.id)
        elif isinstance(node, ast.ImportFrom):
            used.update(f"{node.module}.{alias.name}" for alias in node.names)
    return used

# SPDX-License-Identifier: AGPL-3.0-only
"""Find every read of unified_sites in a source tree and decide, per read, whether it applies
the E4 scope filter (migration 0020). Used by tests/api/test_scope_read_paths.py.

A READ is an SQL string that selects ``FROM``/``JOIN unified_sites``, or an ORM call that
puts ``UnifiedSite`` into a query (``query``, ``join``, ``outerjoin``, ``select``,
``select_from``, ``get``, ``aliased`` - anywhere in the arguments, so
``query(func.count(UnifiedSite.id))`` counts).

Each read is judged ON ITS OWN, not by the function around it. The read's expression (the
whole expression of the statement it sits in) must carry the scope, directly or through
the values it is built from:

* directly: a call or name ``not_retired`` / ``is_retired`` / ``curated_page`` /
  ``card_site_in_scope`` / ``RETIRED``, an attribute ``scope_status``, or SQL text that
  names ``scope_status`` (SQL ``--`` comments stripped first);
* through a module constant or a module function that carries it (a function carries it
  when one of its ``return`` values does);
* through a local name the expression uses, resolved to every value assigned, appended or
  extended into that name in the enclosing functions;
* forward, through the names the read's result is assigned to: ``site = db.get(UnifiedSite,
  i)`` followed by ``if site.scope_status == RETIRED`` handles the scope. Forward
  expressions count only by what they say themselves - otherwise ``return a + b`` would lend
  the filter of query ``a`` to an unfiltered query ``b``.

What never counts: comments (not in the AST), docstrings and other bare string statements,
import statements (``from ... import RETIRED`` is an ``alias``, not a name the code uses),
and a scope token in a DIFFERENT statement of the same function.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

READ_SQL = re.compile(r"(?<!DELETE )\b(?:FROM|JOIN)\s+unified_sites\b", re.IGNORECASE)
_SQL_COMMENT = re.compile(r"--[^\n]*")
ORM_READERS = frozenset({"query", "join", "outerjoin", "get", "select", "select_from", "aliased"})
SCOPE_TOKENS = frozenset(
    {
        "scope_status",
        "not_retired",
        "is_retired",
        "RETIRED",
        "card_site_in_scope",
        "curated_page",  # carries not_retired() - pipeline/utils/public_sites.py
    }
)
#: Calls that put a value into a name: clauses.append(not_retired()), conds.extend(...).
_APPENDERS = frozenset({"append", "extend", "insert", "update", "add"})

_FuncDef = ast.FunctionDef | ast.AsyncFunctionDef


def _is_bare_string(node: ast.AST) -> bool:
    """A docstring, or any other string statement - documentation, never code."""
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _walk_code(node: ast.AST, *, own: bool = False) -> Iterator[ast.AST]:
    """ast.walk without bare string statements (docstrings).

    ``own``: stay in ``node``'s own body - do not descend into a nested function or class,
    whose names are its own (a route factory's sibling routes must not lend each other
    their local values).
    """
    stack = [node]
    while stack:
        current = stack.pop()
        if _is_bare_string(current):
            continue
        yield current
        for child in ast.iter_child_nodes(current):
            if own and isinstance(child, _FuncDef | ast.ClassDef):
                continue
            stack.append(child)


def _tokens(node: ast.AST) -> set[str]:
    """The identifiers the code under ``node`` uses, plus 'scope_status' for SQL naming it."""
    out: set[str] = set()
    for n in _walk_code(node):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
        elif (
            isinstance(n, ast.Constant)
            and isinstance(n.value, str)
            and "scope_status" in _SQL_COMMENT.sub("", n.value)
        ):
            out.add("scope_status")
    return out


def _names(node: ast.AST) -> set[str]:
    return {n.id for n in _walk_code(node) if isinstance(n, ast.Name)}


def _is_unified_site(node: ast.AST) -> bool:
    return any(isinstance(n, ast.Name) and n.id == "UnifiedSite" for n in ast.walk(node))


def _reads_sql(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and bool(READ_SQL.search(_SQL_COMMENT.sub("", node.value)))
    )


def _reads_orm(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
    if name not in ORM_READERS:
        return False
    return any(_is_unified_site(arg) for arg in [*node.args, *(k.value for k in node.keywords)])


@dataclass
class _Scope:
    """Local names of one function: what is put into each, and where each is used."""

    sources: dict[str, list[ast.AST]] = field(default_factory=dict)
    uses: dict[str, list[ast.AST]] = field(default_factory=dict)
    params: set[str] = field(default_factory=set)

    def locals(self) -> set[str]:
        """Names this function binds itself: they shadow a module constant of that name."""
        return self.params | set(self.sources)


class ModuleScan:
    """Reads of unified_sites in one module and whether each applies the scope filter."""

    def __init__(self, source: str) -> None:
        self.tree = ast.parse(source)
        self.parents: dict[ast.AST, ast.AST] = {}
        for node in ast.walk(self.tree):
            for child in ast.iter_child_nodes(node):
                self.parents[child] = node
        self.constants: dict[str, ast.AST] = {}
        for node in self.tree.body:
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
            ):
                self.constants[node.targets[0].id] = node.value
        self.functions: dict[str, list[_FuncDef]] = {}
        for node in ast.walk(self.tree):
            if isinstance(node, _FuncDef):
                self.functions.setdefault(node.name, []).append(node)
        self._scopes: dict[_FuncDef, _Scope] = {}
        self.scoped = self._scoped_names()

    # -- structure ----------------------------------------------------------------------

    def root(self, node: ast.AST) -> ast.AST:
        """The whole expression of the statement ``node`` sits in."""
        while True:
            parent = self.parents.get(node)
            if parent is None or isinstance(parent, ast.stmt | ast.mod):
                return node
            node = parent

    def statement(self, node: ast.AST) -> ast.AST | None:
        parent = self.parents.get(node)
        while parent is not None and not isinstance(parent, ast.stmt):
            parent = self.parents.get(parent)
        return parent

    def enclosing(self, node: ast.AST) -> list[_FuncDef]:
        """Enclosing functions, innermost first."""
        out = []
        parent = self.parents.get(node)
        while parent is not None:
            if isinstance(parent, _FuncDef):
                out.append(parent)
            parent = self.parents.get(parent)
        return out

    def _scope(self, func: _FuncDef) -> _Scope:
        cached = self._scopes.get(func)
        if cached is not None:
            return cached
        scope = _Scope()
        args = func.args
        for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg]:
            if arg is not None:
                scope.params.add(arg.arg)
        for node in _walk_code(func, own=True):
            targets: list[ast.AST] = []
            value: ast.AST | None = None
            if isinstance(node, ast.Assign):
                targets, value = list(node.targets), node.value
            elif isinstance(node, ast.AnnAssign | ast.AugAssign | ast.NamedExpr) and node.value:
                targets, value = [node.target], node.value
            elif isinstance(node, ast.For | ast.AsyncFor | ast.comprehension):
                targets, value = [node.target], node.iter
            elif isinstance(node, ast.withitem) and node.optional_vars is not None:
                targets, value = [node.optional_vars], node.context_expr
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in _APPENDERS
                and isinstance(node.func.value, ast.Name)
            ):
                for arg in node.args:
                    scope.sources.setdefault(node.func.value.id, []).append(arg)
            for target in targets:
                for name in _names(target):
                    scope.sources.setdefault(name, []).append(value)  # type: ignore[arg-type]
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                scope.uses.setdefault(node.id, []).append(self.root(node))
        self._scopes[func] = scope
        return scope

    # -- scope ---------------------------------------------------------------------------

    def _scoped_names(self) -> set[str]:
        """Module constants and functions that carry the scope filter (to a fixpoint)."""
        scoped: set[str] = set()
        changed = True
        while changed:
            changed = False
            for name, value in self.constants.items():
                if name not in scoped and _tokens(value) & (SCOPE_TOKENS | scoped):
                    scoped.add(name)
                    changed = True
            for name, defs in self.functions.items():
                if name in scoped:
                    continue
                returns = [
                    n.value
                    for d in defs
                    for n in _walk_code(d, own=True)
                    if isinstance(n, ast.Return) and n.value is not None
                ]
                if any(self._carries(r, self.enclosing(r), scoped) for r in returns):
                    scoped.add(name)
                    changed = True
        return scoped

    def _names_scope(self, node: ast.AST, funcs: list[_FuncDef], scoped: set[str]) -> bool:
        """``node`` itself names the scope: a scope token, or a scoped module name that no
        enclosing function shadows with a local of the same name."""
        tokens = _tokens(node)
        local: set[str] = set()
        for func in funcs:
            local |= self._scope(func).locals()
        return bool(tokens & SCOPE_TOKENS or (tokens - local) & scoped)

    def _carries(self, expr: ast.AST, funcs: list[_FuncDef], scoped: set[str]) -> bool:
        """``expr``, or a local value it is built from, names the scope."""
        seen: set[str] = set()
        stack = [expr]
        while stack:
            node = stack.pop()
            if self._names_scope(node, funcs, scoped):
                return True
            for name in _names(node) - seen:
                seen.add(name)
                for func in funcs:
                    stack.extend(self._scope(func).sources.get(name, []))
        return False

    def read_filters(self, read: ast.AST) -> bool:
        root = self.root(read)
        funcs = self.enclosing(read)
        if self._carries(root, funcs, self.scoped):
            return True
        # Forward: what the result is assigned to, and what the code says about it.
        stmt = self.statement(read)
        forward: set[str] = set()
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                forward |= _names(target)
        elif isinstance(stmt, ast.AnnAssign | ast.AugAssign):
            forward |= _names(stmt.target)
        elif isinstance(stmt, ast.With | ast.AsyncWith):
            for item in stmt.items:
                if item.optional_vars is not None:
                    forward |= _names(item.optional_vars)
        elif isinstance(stmt, ast.For | ast.AsyncFor):
            forward |= _names(stmt.target)
        seen: set[str] = set()
        while forward - seen:
            name = (forward - seen).pop()
            seen.add(name)
            for func in funcs[:1]:
                for use in self._scope(func).uses.get(name, []):
                    if use is root:
                        continue
                    if self._names_scope(use, funcs, self.scoped):
                        return True
                    use_stmt = self.statement(use)
                    if isinstance(use_stmt, ast.Assign):
                        for target in use_stmt.targets:
                            forward |= _names(target)
        return False

    def reads(self) -> Iterator[tuple[str, int, bool]]:
        """(key, line, filters) per read; key is the innermost function or module constant."""
        for node in ast.walk(self.tree):
            parent = self.parents.get(node)
            if parent is not None and _is_bare_string(parent):
                continue
            if not (_reads_sql(node) or _reads_orm(node)):
                continue
            funcs = self.enclosing(node)
            if funcs:
                key = funcs[0].name
                filters = self.read_filters(node)
            else:
                const = self.statement(node)
                if not (
                    isinstance(const, ast.Assign)
                    and const in self.tree.body
                    and isinstance(const.targets[0], ast.Name)
                ):
                    raise AssertionError(f"line {node.lineno}: read outside any function")
                key = f"<module>:{const.targets[0].id}"
                filters = const.targets[0].id in self.scoped
            yield key, node.lineno, filters


def read_paths(repo: Path, roots: list[Path]) -> dict[str, bool]:
    """{"path::key": filters} for every read of unified_sites in ``roots`` (dirs or files).

    A key filters only when every read under it does.
    """
    found: dict[str, bool] = {}
    for root in roots:
        for path in [root] if root.is_file() else sorted(root.rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            if "unified_sites" not in source and "UnifiedSite" not in source:
                continue
            rel = path.relative_to(repo).as_posix()
            for key, _line, filters in ModuleScan(source).reads():
                full = f"{rel}::{key}"
                found[full] = found.get(full, True) and filters
    return found

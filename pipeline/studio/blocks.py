"""The renderer's block registry (video/src/blocks/registry.json) and props validation.

Contract with the renderer (stream D writes the file, this module reads it at runtime):

    {"blocks": {"<BlockName>": {"props": <JSON schema, type "object">,
                                "map": <bool: the block shows Mapbox/OSM map content>,
                                "platform": <bool: the block is a platform moment>,
                                "drawn": [<prop path whose strings the block draws>]}}}

`drawn` is stream D's one definition of the strings a block draws as text (owner decision 32:
the brand-font glyph rule covers only those): keys joined by ".", a key suffixed "[]" for every
element of an array ("claims[].label", "hypotheses[]"). Each path must lead through the props
schema to a string; ids, paths, URLs other than ShareCard's and a SourceViewer's quote (pixels
of the captured page) are not drawn as text.

The props schemas use this JSON Schema subset and nothing else (anything else is refused at
load, so a schema can never be silently half-checked): type (string or list of: string,
number, integer, boolean, object, array, null), properties, required, additionalProperties
(bool or schema), items, enum, minimum, maximum, minItems, maxItems, minLength, maxLength,
and the annotations description, title, default, $comment.

Props are validated after {"$ref"}/{"$capture"} resolution (casefile.resolve_refs), i.e.
against what the block will actually receive.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.studio.config import REPO
from pipeline.studio.errors import StudioError

REGISTRY_PATH = REPO / "video" / "src" / "blocks" / "registry.json"
FORBIDDEN_BLOCKS = frozenset({"TitleCard", "Agent", "Character", "Avatar", "Presenter", "Host"})
SUPPORTED_KEYWORDS = frozenset(
    {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "enum",
        "minimum",
        "maximum",
        "minItems",
        "maxItems",
        "minLength",
        "maxLength",
        "description",
        "title",
        "default",
        "$comment",
    }
)
TYPES = frozenset({"string", "number", "integer", "boolean", "object", "array", "null"})


class RegistryError(StudioError):
    """registry.json breaks the contract above."""


def _check_schema(schema: Any, path: str) -> list[str]:
    if not isinstance(schema, dict):
        return [f"{path}: a schema must be an object"]
    problems = [
        f"{path}: unsupported keyword {k!r}" for k in sorted(set(schema) - SUPPORTED_KEYWORDS)
    ]
    types = schema.get("type")
    if types is not None:
        listed = types if isinstance(types, list) else [types]
        bad = [t for t in listed if t not in TYPES]
        if bad:
            problems.append(f"{path}: unknown type {bad}")
    for name, sub in (schema.get("properties") or {}).items():
        problems.extend(_check_schema(sub, f"{path}.properties.{name}"))
    if isinstance(schema.get("additionalProperties"), dict):
        problems.extend(
            _check_schema(schema["additionalProperties"], f"{path}.additionalProperties")
        )
    if "items" in schema:
        problems.extend(_check_schema(schema["items"], f"{path}.items"))
    return problems


def drawn_path_problem(schema: dict[str, Any], pattern: str) -> str | None:
    """None when `pattern` (a registry `drawn` path) leads through `schema` to a string."""
    node = schema
    for segment in pattern.split("."):
        key = segment.removesuffix("[]")
        properties = node.get("properties") or {}
        if key not in properties:
            return f"{pattern!r}: no property {key!r}"
        node = properties[key]
        if segment.endswith("[]"):
            if "items" not in node:
                return f"{pattern!r}: {key} is not an array"
            node = node["items"]
    types = node.get("type")
    if "string" not in (types if isinstance(types, list) else [types]):
        return f"{pattern!r} does not lead to a string"
    return None


def validate_registry(data: Any) -> list[str]:
    if (
        not isinstance(data, dict)
        or set(data) != {"blocks"}
        or not isinstance(data["blocks"], dict)
    ):
        return ['registry.json must be {"blocks": {name: {props, map, platform, drawn}}}']
    problems: list[str] = []
    for name, entry in data["blocks"].items():
        if name in FORBIDDEN_BLOCKS:
            problems.append(f"{name}: title-card and on-screen agent blocks are not allowed")
        if not isinstance(entry, dict) or set(entry) != {"props", "map", "platform", "drawn"}:
            problems.append(f"{name}: entry must be exactly {{props, map, platform, drawn}}")
            continue
        if not isinstance(entry["map"], bool) or not isinstance(entry["platform"], bool):
            problems.append(f"{name}: map and platform must be booleans")
        drawn = entry["drawn"]
        drawn_ok = isinstance(drawn, list) and all(isinstance(p, str) and p for p in drawn)
        if not drawn_ok:
            problems.append(f"{name}: drawn must be a list of prop paths (non-empty strings)")
        if not isinstance(entry["props"], dict) or entry["props"].get("type") != "object":
            problems.append(f"{name}: props must be a schema of type 'object'")
            continue
        problems.extend(_check_schema(entry["props"], f"{name}.props"))
        if drawn_ok:
            found = (drawn_path_problem(entry["props"], pattern) for pattern in drawn)
            problems.extend(f"{name}.drawn: {p}" for p in found if p is not None)
    return problems


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, dict[str, Any]]:
    if not path.exists():
        raise RegistryError(f"{path} does not exist: the renderer's block registry is missing")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RegistryError(f"registry.json is not valid JSON: {exc}") from exc
    problems = validate_registry(data)
    if problems:
        raise RegistryError("; ".join(problems))
    return data["blocks"]


def claim_icons(registry: dict[str, dict[str, Any]]) -> tuple[str, ...]:
    """The ClaimBoard icon names the renderer draws (the case file's claim icons)."""
    claims = registry["ClaimBoard"]["props"]["properties"]["claims"]
    return tuple(claims["items"]["properties"]["icon"]["enum"])


def _type_ok(value: Any, t: str) -> bool:
    if t == "null":
        return value is None
    if t == "boolean":
        return isinstance(value, bool)
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "string":
        return isinstance(value, str)
    if t == "array":
        return isinstance(value, list)
    return isinstance(value, dict)


def props_errors(schema: dict[str, Any], value: Any, path: str = "props") -> list[str]:
    """Every way `value` breaks `schema` (the subset above)."""
    types = schema.get("type")
    if types is not None:
        listed = types if isinstance(types, list) else [types]
        if not any(_type_ok(value, t) for t in listed):
            return [f"{path}: expected {'/'.join(listed)}"]
    problems: list[str] = []
    if "enum" in schema and value not in schema["enum"]:
        problems.append(f"{path}: {value!r} is not one of {schema['enum']}")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            problems.append(f"{path}: shorter than {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            problems.append(f"{path}: longer than {schema['maxLength']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            problems.append(f"{path}: below {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            problems.append(f"{path}: above {schema['maximum']}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            problems.append(f"{path}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            problems.append(f"{path}: more than {schema['maxItems']} items")
        if "items" in schema:
            for i, item in enumerate(value):
                problems.extend(props_errors(schema["items"], item, f"{path}[{i}]"))
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                problems.append(f"{path}.{key}: missing")
        extra = schema.get("additionalProperties", True)
        for key, sub in value.items():
            if key in props:
                problems.extend(props_errors(props[key], sub, f"{path}.{key}"))
            elif extra is False:
                problems.append(f"{path}.{key}: not allowed")
            elif isinstance(extra, dict):
                problems.extend(props_errors(extra, sub, f"{path}.{key}"))
    return problems

"""Tiny JSON-Schema subset validator (type, enum, required, properties, items, min/max, oneOf-by-const).

One schema per referee tool serves three jobs: constrained decoding (llama.cpp grammar),
the tool documentation shown to the model, and argument validation here.
"""
from __future__ import annotations

_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool,
          "integer": int, "number": (int, float), "null": type(None)}


def validate(value, schema: dict, path: str = "args") -> list[str]:
    errs: list[str] = []
    t = schema.get("type")
    if t:
        ts = t if isinstance(t, list) else [t]
        ok = False
        for x in ts:
            py = _TYPES[x]
            if isinstance(value, py) and not (x in ("integer", "number") and isinstance(value, bool)):
                if x == "integer" and isinstance(value, float): continue
                ok = True; break
        if not ok:
            return [f"{path}: expected {'/'.join(ts)}, got {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{path}: must be one of {schema['enum']}, got {value!r}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]: errs.append(f"{path}: must be >= {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]: errs.append(f"{path}: must be <= {schema['maximum']}")
    if isinstance(value, str):
        if "minLength" in schema and len(value.strip()) < schema["minLength"]:
            errs.append(f"{path}: needs at least {schema['minLength']} characters")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]: errs.append(f"{path}: needs >= {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]: errs.append(f"{path}: at most {schema['maxItems']} items")
        if "items" in schema:
            for i, v in enumerate(value):
                errs += validate(v, schema["items"], f"{path}[{i}]")
    if isinstance(value, dict):
        for r in schema.get("required", []):
            if r not in value:
                errs.append(f"{path}: missing required field {r!r}")
        props = schema.get("properties", {})
        for k, v in value.items():
            if k in props:
                errs += validate(v, props[k], f"{path}.{k}")
            elif schema.get("additionalProperties") is False:
                errs.append(f"{path}: unknown field {k!r} (allowed: {sorted(props)})")
    return errs


def render(schema: dict, indent: int = 0) -> str:
    """Compact one-line-per-field documentation of a schema, for the model."""
    pad = "  " * indent
    props, req = schema.get("properties", {}), set(schema.get("required", []))
    lines = []
    for k, s in props.items():
        t = s.get("type", "any")
        t = "|".join(t) if isinstance(t, list) else t
        extra = ""
        if "enum" in s: extra = " one of " + "/".join(map(str, s["enum"]))
        if t == "array" and s.get("items", {}).get("type") == "object":
            extra = " of objects:"
        elif t == "array":
            extra = f" of {s.get('items', {}).get('type', 'any')}"
        mark = "" if k in req else "?"
        d = s.get("description", "")
        lines.append(f"{pad}{k}{mark}: {t}{extra}" + (f" — {d}" if d else ""))
        if t == "object" and s.get("properties"):
            lines.append(render(s, indent + 1))
        elif t == "array" and s.get("items", {}).get("type") == "object":
            lines.append(render(s["items"], indent + 1))
    return "\n".join(lines)

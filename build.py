#!/usr/bin/env python3
"""
Compile the DTCG token source into figma-variables.json, the file the
importer plugin reads.

    python3 build.py

Source of truth stays in core.json / semantic/*.json / component.json.
Everything Figma can't represent as a variable (typography and shadow
composites) is emitted as style definitions instead, and anything that
can't cross over at all is listed in the skip report.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
REF = re.compile(r"^\{([^}]+)\}$")

# Tokens Studio / DTCG type -> Figma variable type
FLOAT_TYPES = {"spacing", "sizing", "borderRadius", "borderWidth", "fontSizes", "dimension", "opacity"}
STRING_TYPES = {"fontFamilies", "fontWeights"}
STYLE_TYPES = {"typography", "boxShadow"}
# Percentage-based; Figma variables only accept absolute numbers for these
SKIP_TYPES = {"lineHeights", "letterSpacing", "other"}

skipped: list[tuple[str, str, str]] = []


def load(path: str) -> dict:
    with open(ROOT / path) as f:
        return json.load(f)


def flatten(node: dict, prefix: str = "") -> dict:
    """Collapse nested token groups into {dotted.path: token}."""
    if isinstance(node, dict) and "$value" in node:
        return {prefix: node}
    out = {}
    for key, val in node.items():
        if key.startswith("$") or not isinstance(val, dict):
            continue
        out.update(flatten(val, f"{prefix}.{key}" if prefix else key))
    return out


core = flatten(load("core.json"))
light = flatten(load("semantic/light.json"))
dark = flatten(load("semantic/dark.json"))
component = flatten(load("component.json"))

# Which collection does a given token path live in?
OWNER = {}
for path in core:
    OWNER[path] = "Primitives"
for path in light:
    OWNER[path] = "Semantic"
for path in component:
    OWNER[path] = "Component"


def var_name(path: str) -> str:
    """Dots become slashes, which Figma renders as variable groups."""
    return path.replace(".", "/")


def resolve_alias(value):
    """Turn {token.path} into an {"alias": "Collection/var/name"} pointer."""
    if not isinstance(value, str):
        return None
    match = REF.match(value.strip())
    if not match:
        return None
    target = match.group(1)
    collection = OWNER.get(target)
    if collection is None:
        raise KeyError(f"unresolved reference: {{{target}}}")
    return {"alias": f"{collection}/{var_name(target)}"}


def number(value):
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text.endswith("%"):
        return round(float(text[:-1]) / 100, 4)
    return float(re.sub(r"[^0-9.\-]", "", text))


def figma_type(token_type: str):
    if token_type == "color":
        return "COLOR"
    if token_type in FLOAT_TYPES:
        return "FLOAT"
    if token_type in STRING_TYPES:
        return "STRING"
    return None


def scopes_for(path: str, token_type: str, collection: str) -> list[str]:
    """Limit where each variable shows up in Figma's picker."""
    last = path.split(".")[-1]
    if token_type == "color":
        if collection == "Primitives":
            return ["ALL_SCOPES"]
        if path.startswith("fg.") or last == "fg" or last.startswith("fg-") \
                or last in {"placeholder", "on-solid", "solid-fg", "link", "link-hover"}:
            return ["TEXT_FILL", "SHAPE_FILL"]
        if path.startswith("border.") or "border" in last or last == "ring":
            return ["STROKE_COLOR"]
        return ["FRAME_FILL", "SHAPE_FILL"]
    return {
        "spacing": ["GAP", "WIDTH_HEIGHT"],
        "sizing": ["WIDTH_HEIGHT"],
        "borderRadius": ["CORNER_RADIUS"],
        "borderWidth": ["STROKE_FLOAT"],
        "fontSizes": ["FONT_SIZE"],
        "opacity": ["OPACITY"],
        "dimension": ["WIDTH_HEIGHT"],
        "fontFamilies": ["FONT_FAMILY"],
        "fontWeights": ["FONT_STYLE"],
    }.get(token_type, ["ALL_SCOPES"])


def code_syntax(path: str) -> dict:
    return {"WEB": "--" + path.replace(".", "-")}


def build_variable(path: str, token: dict, collection: str, values: dict):
    token_type = token["$type"]
    ftype = figma_type(token_type)
    if ftype is None:
        return None
    entry = {
        "name": var_name(path),
        "type": ftype,
        "scopes": scopes_for(path, token_type, collection),
        "codeSyntax": code_syntax(path),
        "values": values,
    }
    if token.get("$description"):
        entry["description"] = token["$description"]
    return entry


def convert(raw, token_type: str):
    """A raw token value becomes either an alias pointer or a literal."""
    alias = resolve_alias(raw)
    if alias:
        return alias
    if token_type == "color" or token_type in STRING_TYPES:
        return raw
    return number(raw)


# --- Primitives: everything in core except composites -----------------------

primitives = []
for path, token in core.items():
    token_type = token["$type"]
    if token_type in STYLE_TYPES:
        continue  # handled as styles below
    if token_type in SKIP_TYPES:
        skipped.append((path, token_type, "percentage or non-visual value; lives in text styles instead"))
        continue
    entry = build_variable(path, token, "Primitives", {"Value": convert(token["$value"], token_type)})
    if entry:
        primitives.append(entry)

# --- Semantic: same names, one value per mode -------------------------------

missing = set(light) ^ set(dark)
if missing:
    sys.exit(f"Light and dark sets are out of sync: {sorted(missing)}")

semantic = []
for path, token in light.items():
    token_type = token["$type"]
    if token_type in STYLE_TYPES:
        continue
    if token_type in SKIP_TYPES:
        skipped.append((path, token_type, "percentage or non-visual value"))
        continue
    entry = build_variable(path, token, "Semantic", {
        "Light": convert(token["$value"], token_type),
        "Dark": convert(dark[path]["$value"], token_type),
    })
    if entry:
        semantic.append(entry)

# --- Component --------------------------------------------------------------

components = []
for path, token in component.items():
    token_type = token["$type"]
    if token_type in STYLE_TYPES:
        skipped.append((path, token_type, "shadow reference; apply the effect style directly"))
        continue
    entry = build_variable(path, token, "Component", {"Value": convert(token["$value"], token_type)})
    if entry:
        components.append(entry)

# --- Text styles ------------------------------------------------------------


def deref(value):
    """Follow a {reference} to its literal value, through any depth."""
    seen = 0
    while isinstance(value, str) and REF.match(value.strip()):
        target = REF.match(value.strip()).group(1)
        source = core.get(target) or light.get(target) or component.get(target)
        if source is None:
            raise KeyError(f"unresolved reference: {{{target}}}")
        value = source["$value"]
        seen += 1
        if seen > 10:
            raise RecursionError(f"reference loop at {target}")
    return value


def percent(value):
    text = str(deref(value)).strip()
    return {"unit": "PERCENT", "value": float(text.rstrip("%"))}


STYLE_NAMES = {
    "display": "Display",
    "heading-xl": "Heading/XL",
    "heading-lg": "Heading/LG",
    "heading-md": "Heading/MD",
    "heading-sm": "Heading/SM",
    "body-lg": "Body/LG",
    "body-md": "Body/MD",
    "body-sm": "Body/SM",
    "label-md": "Label/MD",
    "label-sm": "Label/SM",
    "overline": "Overline",
    "code": "Code",
}

text_styles = []
for path, token in core.items():
    if token["$type"] != "typography":
        continue
    key = path.split(".", 1)[1]
    value = token["$value"]
    style = {
        "name": STYLE_NAMES.get(key, key.title()),
        "fontFamily": deref(value["fontFamily"]),
        "fontStyle": deref(value["fontWeight"]),
        "fontSize": number(deref(value["fontSize"])),
        "lineHeight": percent(value["lineHeight"]),
        "letterSpacing": percent(value["letterSpacing"]),
        "textCase": {"uppercase": "UPPER", "lowercase": "LOWER"}.get(value.get("textCase"), "ORIGINAL"),
    }
    if token.get("$description"):
        style["description"] = token["$description"]
    text_styles.append(style)

# --- Effect styles ----------------------------------------------------------

effect_styles = []
for mode_name, token_set in (("Light", light), ("Dark", dark)):
    for path, token in token_set.items():
        if token["$type"] != "boxShadow":
            continue
        key = path.split(".", 1)[1]
        shadows = token["$value"]
        if not isinstance(shadows, list):
            shadows = [shadows]
        if all(float(s["blur"]) == 0 and float(s["y"]) == 0 for s in shadows):
            continue  # the "flat" no-op token
        effect_styles.append({
            "name": f"Elevation/{mode_name}/{key.title()}",
            "effects": [{
                "type": "DROP_SHADOW",
                "color": s["color"],
                "offset": {"x": float(s["x"]), "y": float(s["y"])},
                "radius": float(s["blur"]),
                "spread": float(s.get("spread", 0)),
            } for s in shadows],
            "description": token.get("$description", ""),
        })

# --- Emit -------------------------------------------------------------------

output = {
    "collections": [
        {"name": "Primitives", "modes": ["Value"], "variables": primitives},
        {"name": "Semantic", "modes": ["Light", "Dark"], "variables": semantic},
        {"name": "Component", "modes": ["Value"], "variables": components},
    ],
    "textStyles": text_styles,
    "effectStyles": effect_styles,
}

target = ROOT / "figma-variables.json"
with open(target, "w") as f:
    json.dump(output, f, indent=2)
    f.write("\n")

print(f"Wrote {target.relative_to(ROOT)}")
for collection in output["collections"]:
    modes = ", ".join(collection["modes"])
    print(f"  {collection['name']:12s} {len(collection['variables']):4d} variables   modes: {modes}")
print(f"  {'Text styles':12s} {len(text_styles):4d}")
print(f"  {'Effect styles':12s} {len(effect_styles):4d}")

if skipped:
    print(f"\nNot importable as variables ({len(skipped)}):")
    for path, token_type, why in skipped:
        print(f"  {path:28s} ({token_type}) — {why}")

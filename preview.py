#!/usr/bin/env python3
"""
Generate preview.html — a browsable specimen of the token system.

    python3 preview.py

Everything on the page is derived from the token JSON, so the preview can't
drift from what actually imports into Figma. Semantic values are emitted for
both modes and swapped with a data-theme attribute, which means the light/dark
toggle exercises the real alias chains rather than a parallel set of colours.
"""

import json
import re
from html import escape
from pathlib import Path

ROOT = Path(__file__).parent
REF = re.compile(r"^\{([^}]+)\}$")

PX_TYPES = {"spacing", "sizing", "borderRadius", "borderWidth", "fontSizes", "dimension"}


def load(path):
    with open(ROOT / path) as f:
        return json.load(f)


def flatten(node, prefix=""):
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


def ref_target(value):
    if not isinstance(value, str):
        return None
    match = REF.match(value.strip())
    return match.group(1) if match else None


def var_name(path):
    return "--" + path.replace(".", "-")


def num(value):
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text.endswith("%"):
        return float(text[:-1])
    return float(re.sub(r"[^0-9.\-]", "", text))


def lookup(path, semantic):
    return component.get(path) or semantic.get(path) or core.get(path)


def chain(path, semantic):
    """Walk the alias chain from a token down to its literal value."""
    steps = [path]
    token = lookup(path, semantic)
    value = token["$value"]
    while (target := ref_target(value)) is not None:
        steps.append(target)
        value = lookup(target, semantic)["$value"]
    return steps, value


def css_value(token):
    """Emit a CSS value, keeping references as var() so the chain survives."""
    ttype, value = token["$type"], token["$value"]
    target = ref_target(value)
    if target:
        return f"var({var_name(target)})"
    if ttype == "color":
        return value
    if ttype in PX_TYPES:
        return f"{num(value):g}px"
    if ttype == "opacity":
        return f"{num(value) / 100:g}"
    if ttype == "lineHeights":
        return f"{num(value):g}%"
    if ttype == "letterSpacing":
        return f"{num(value) / 100:g}em"
    if ttype == "fontFamilies":
        return f"'{value}'"
    return str(value)


def shadow_css(token):
    shadows = token["$value"]
    if not isinstance(shadows, list):
        shadows = [shadows]
    return ", ".join(
        f"{num(s['x']):g}px {num(s['y']):g}px {num(s['blur']):g}px {num(s.get('spread', 0)):g}px {s['color']}"
        for s in shadows
    )


# ---------------------------------------------------------------- CSS tokens

def declarations(tokens, indent="  "):
    lines = []
    for path, token in tokens.items():
        if token["$type"] == "typography":
            continue
        if token["$type"] == "boxShadow" and not ref_target(token["$value"]):
            value = shadow_css(token)
        else:
            value = css_value(token)
        lines.append(f"{indent}{var_name(path)}: {value};")
    return "\n".join(lines)


primitive_css = declarations(core)
light_css = declarations(light)
dark_css = declarations(dark)
component_css = declarations(component)

# --------------------------------------------------------------- HTML pieces


def token_row(path, semantic_light, kind="color"):
    """One specimen row: swatch, name, and its resolution chain per mode."""
    var = var_name(path)
    chains = {}
    for mode, semantic in (("light", light), ("dark", dark)):
        steps, literal = chain(path, semantic)
        hops = "".join(
            f'<span class="hop">{escape(step.replace(".", "/"))}</span>'
            f'{"<i>&rarr;</i>" if i < len(steps) - 1 else ""}'
            for i, step in enumerate(steps)
        )
        value = literal if kind == "color" else f"{num(literal):g}px"
        chains[mode] = (
            f'<div class="chain chain-{mode}">{hops}'
            f'<code class="literal" data-resolves="{steps[-1]}">'
            f'{escape(str(value))}</code></div>'
        )
    return (
        f'<div class="row">'
        f'<span class="swatch" style="background:var({var})"></span>'
        f'<div class="row-body">'
        f'<button class="tname" data-copy="{escape(var)}">{escape(var)}</button>'
        f'{chains["light"]}{chains["dark"]}'
        f"</div></div>"
    )


def section(anchor, title, blurb, body):
    return (
        f'<section id="{anchor}">'
        f"<h2>{escape(title)}</h2>"
        f'<p class="blurb">{blurb}</p>'
        f"{body}</section>"
    )


def group(title, rows):
    return f'<h3>{escape(title)}</h3><div class="rows">{"".join(rows)}</div>'


def ramp(name, label):
    steps = [(p, t) for p, t in core.items() if p.startswith(f"color.{name}.")]
    chips = "".join(
        f'<button class="chip" data-copy="{var_name(p)}">'
        f'<span class="chip-color" style="background:var({var_name(p)})"></span>'
        f'<span class="chip-step">{p.split(".")[-1]}</span>'
        f'<span class="chip-hex" data-resolves="{p}">{t["$value"]}</span></button>'
        for p, t in steps
    )
    return f'<div class="ramp"><h4>{escape(label)}</h4><div class="chips">{chips}</div></div>'


# Brand ---------------------------------------------------------------------

brand_steps = [(p, t) for p, t in core.items() if p.startswith("color.brand.")]
brand_hero = f"""
<div class="hero">
  <div class="hero-mark">
    <span class="hero-swatch" style="background:var(--color-brand-600)"></span>
    <span class="hero-swatch" style="background:var(--color-brand-500)"></span>
    <span class="hero-swatch" style="background:var(--color-brand-400)"></span>
  </div>
  <div class="hero-copy">
    <p>The brand ramp is the only place a hue is chosen for its own sake. Step
    <code>600</code> carries solid actions in light mode, <code>500</code> in dark —
    every other brand decision aliases one of those two.</p>
    <div class="hero-pairs">
      <div class="pair" style="background:var(--color-brand-600);color:#fff">
        <b>Aa</b><span>brand/600 &middot; white &middot; 6.78:1</span>
      </div>
      <div class="pair" style="background:var(--color-brand-50);color:var(--color-brand-800)">
        <b>Aa</b><span>brand/50 &middot; brand/800 &middot; 11.2:1</span>
      </div>
    </div>
  </div>
</div>
"""
brand_body = brand_hero + f'<div class="ramps">{ramp("brand", "color/brand")}</div>' + group(
    "Brand roles",
    [token_row(p, light) for p in ("fg.brand", "border.brand", "focus.ring",
                                   "action.primary.bg", "action.primary.bg-hover",
                                   "action.primary.bg-active", "action.primary.fg")],
)

# Semantic ------------------------------------------------------------------

SEMANTIC_GROUPS = [
    ("Surfaces", lambda p: p.startswith("bg.")),
    ("Text", lambda p: p.startswith("fg.")),
    ("Borders", lambda p: p.startswith("border.") or p == "focus.ring" or p == "focus.offset"),
    ("Actions", lambda p: p.startswith("action.")),
    ("Fields", lambda p: p.startswith("field.")),
    ("Status", lambda p: p.startswith("status.")),
]
semantic_body = "".join(
    group(title, [token_row(p, light) for p, t in light.items()
                  if test(p) and t["$type"] == "color"])
    for title, test in SEMANTIC_GROUPS
)

# Typography ----------------------------------------------------------------

TYPE_ORDER = ["display", "heading-xl", "heading-lg", "heading-md", "heading-sm",
              "body-lg", "body-md", "body-sm", "label-md", "label-sm", "overline", "code"]
SPECIMEN = {
    "display": "Tokens, not values",
    "heading-xl": "A single source of truth",
    "heading-lg": "Three tiers, one direction",
    "heading-md": "Semantic names describe jobs",
    "heading-sm": "Components compose roles",
    "body-lg": "Primitives hold raw values and no opinions.",
    "body-md": "The semantic layer assigns each value a job, so a rebrand touches core and nothing else has to move.",
    "body-sm": "Component tokens alias semantic roles, which is what lets a card follow whichever mode its frame is set to.",
    "label-md": "Save changes",
    "label-sm": "Optional",
    "overline": "Foundations",
    "code": "var(--bg-surface)",
}

type_rows = []
for key in TYPE_ORDER:
    token = core[f"text.{key}"]
    value = token["$value"]
    spec = " · ".join([
        ref_target(value["fontFamily"]).split(".")[-1],
        ref_target(value["fontWeight"]).split(".")[-1],
        f'{num(core[ref_target(value["fontSize"])]["$value"]):g}px',
        f'{num(core[ref_target(value["lineHeight"])]["$value"]):g}% leading',
        f'{num(core[ref_target(value["letterSpacing"])]["$value"]):g}% tracking',
    ])
    type_rows.append(
        f'<div class="type-row">'
        f'<div class="type-meta"><button class="tname" data-copy="text/{key}">text/{key}</button>'
        f'<span class="spec">{escape(spec)}</span></div>'
        f'<div class="specimen text-{key}">{escape(SPECIMEN[key])}</div>'
        f"</div>"
    )
type_body = "".join(type_rows)

# Spacing -------------------------------------------------------------------

space_rows = "".join(
    f'<div class="scale-row">'
    f'<button class="tname" data-copy="{var_name(p)}">{escape(var_name(p))}</button>'
    f'<span class="bar" style="width:{min(num(t["$value"]), 200):g}px"></span>'
    f'<code class="literal">{num(t["$value"]):g}px</code></div>'
    for p, t in core.items() if p.startswith("space.")
)
space_body = f'<div class="scale">{space_rows}</div>'

# Radius and stroke ---------------------------------------------------------

radius_tiles = "".join(
    f'<button class="tile" data-copy="{var_name(p)}" style="border-radius:var({var_name(p)})">'
    f'<span>{p.split(".")[-1]}</span><code>{num(t["$value"]):g}</code></button>'
    for p, t in core.items() if p.startswith("radius.")
)
stroke_tiles = "".join(
    f'<button class="tile stroke" data-copy="{var_name(p)}" style="border-width:var({var_name(p)})">'
    f'<span>{p.split(".")[-1]}</span><code>{num(t["$value"]):g}</code></button>'
    for p, t in core.items() if p.startswith("borderWidth.")
)
shape_body = (
    f'<h3>Radius</h3><div class="tiles">{radius_tiles}</div>'
    f'<h3>Stroke width</h3><div class="tiles">{stroke_tiles}</div>'
)

# Elevation -----------------------------------------------------------------

elevation_cards = "".join(
    f'<button class="elev" data-copy="{var_name(p)}" style="box-shadow:var({var_name(p)})">'
    f'<b>{p.split(".")[-1]}</b><code>{escape(var_name(p))}</code></button>'
    for p in light if p.startswith("elevation.")
)
elevation_body = (
    f'<div class="elevs">{elevation_cards}</div>'
    '<p class="aside">Shadows import as effect styles, one set per mode. They are the one '
    'part of the system that does not follow a mode switch on its own.</p>'
)

# Components ----------------------------------------------------------------

components_body = """
<h3>Button</h3>
<div class="demo">
  <div class="btn-row">
    <button class="btn primary sm">Save changes</button>
    <button class="btn primary md">Save changes</button>
    <button class="btn primary lg">Save changes</button>
  </div>
  <div class="btn-row">
    <button class="btn primary md">Primary</button>
    <button class="btn secondary md">Secondary</button>
    <button class="btn ghost md">Ghost</button>
    <button class="btn destructive md">Delete</button>
    <button class="btn primary md" disabled>Disabled</button>
  </div>
</div>

<h3>Field</h3>
<div class="demo">
  <div class="field">
    <label for="p-email">Email address</label>
    <input id="p-email" type="email" placeholder="you@example.com">
    <span class="help">We only use this to send receipts.</span>
  </div>
  <div class="field error">
    <label for="p-name">Workspace name</label>
    <input id="p-name" type="text" value="my workspace!">
    <span class="help">Use letters, numbers, and hyphens only.</span>
  </div>
</div>

<h3>Card</h3>
<div class="demo cards">
  <article class="card">
    <span class="badge success">Published</span>
    <h4>Semantic layer</h4>
    <p>Names the job a value does, so the same token means the same thing in both modes.</p>
    <button class="btn secondary sm">View tokens</button>
  </article>
  <article class="card">
    <span class="badge info">Draft</span>
    <h4>Component layer</h4>
    <p>Composes semantic roles into per-component decisions like padding and radius.</p>
    <button class="btn secondary sm">View tokens</button>
  </article>
</div>

<h3>Status</h3>
<div class="demo badges">
  <span class="badge success">Success</span>
  <span class="badge warning">Warning</span>
  <span class="badge danger">Danger</span>
  <span class="badge info">Info</span>
</div>

<h3>Menu</h3>
<div class="demo">
  <div class="menu">
    <button class="menu-item">Duplicate</button>
    <button class="menu-item">Rename</button>
    <button class="menu-item">Move to&hellip;</button>
    <button class="menu-item danger">Delete</button>
  </div>
</div>

<h3>Motion</h3>
<p class="aside">Duration and easing have no Figma variable type, so they live here and in
code export only. Hover each square.</p>
<div class="demo motion">
  <button class="moves" style="transition-duration:var(--duration-instant)"><code>instant</code></button>
  <button class="moves" style="transition-duration:var(--duration-fast)"><code>fast</code></button>
  <button class="moves" style="transition-duration:var(--duration-normal)"><code>normal</code></button>
  <button class="moves" style="transition-duration:var(--duration-slow)"><code>slow</code></button>
</div>
"""

# Primitives ----------------------------------------------------------------

RAMPS = [("neutral", "color/neutral"), ("brand", "color/brand"), ("accent", "color/accent"),
         ("success", "color/success"), ("warning", "color/warning"),
         ("danger", "color/danger"), ("info", "color/info")]
primitives_body = (
    f'<div class="ramps">{"".join(ramp(n, l) for n, l in RAMPS)}</div>'
    + group("Alpha", [])
    + f'<div class="chips alpha">'
    + "".join(
        f'<button class="chip" data-copy="{var_name(p)}">'
        f'<span class="chip-color checker" style="background-color:{t["$value"]}"></span>'
        f'<span class="chip-step">{p.split(".")[-1]}</span></button>'
        for p, t in core.items() if p.startswith("color.alpha.")
    )
    + "</div>"
    + '<h3>Type scale</h3><div class="scale">'
    + "".join(
        f'<div class="scale-row">'
        f'<button class="tname" data-copy="{var_name(p)}">{escape(var_name(p))}</button>'
        f'<span class="sizer" style="font-size:var({var_name(p)})">Ag</span>'
        f'<code class="literal">{num(t["$value"]):g}px</code></div>'
        for p, t in core.items() if p.startswith("font.size.")
    )
    + "</div>"
    + '<h3>Sizing</h3><div class="scale">'
    + "".join(
        f'<div class="scale-row">'
        f'<button class="tname" data-copy="{var_name(p)}">{escape(var_name(p))}</button>'
        f'<span class="bar" style="width:{min(num(t["$value"]) / 4, 200):g}px"></span>'
        f'<code class="literal">{num(t["$value"]):g}px</code></div>'
        for p, t in core.items() if p.startswith("size.")
    )
    + "</div>"
)

SECTIONS = [
    ("brand", "Brand", "Where the identity is decided. Everything downstream points here.", brand_body),
    ("semantic", "Semantic colour", "Roles, not values. Each token holds one meaning and two answers — "
     "toggle the mode to watch the chain re-resolve.", semantic_body),
    ("type", "Typography", "Composite tokens that import as Figma text styles.", type_body),
    ("space", "Spacing", "A 4px base with two sub-steps for optical corrections.", space_body),
    ("shape", "Radius &amp; stroke", "Shape values shared across every surface and control.", shape_body),
    ("elevation", "Elevation", "Four depths, tuned separately per mode.", elevation_body),
    ("components", "Components", "The layers working together, built only from tokens.", components_body),
    ("primitives", "Primitives", "The raw material. Nothing in a design should reference this layer directly.", primitives_body),
]

nav = "".join(
    f'<a href="#{anchor}" data-nav="{anchor}">{title}</a>'
    for anchor, title, _, _ in SECTIONS
)
body = "".join(section(a, re.sub("&amp;", "&", t), b, c) for a, t, b, c in SECTIONS)

def available_families():
    """Offer only families actually present in fonts/, per build_fonts.py's manifest.

    Monospaced faces float to the top of the mono list; otherwise every family is
    offered for every slot, since which face suits a display role is a judgement
    call rather than something to infer from a filename.
    """
    manifest = ROOT / "fonts" / "fonts.json"
    if not manifest.exists():
        # No manifest yet — fall back to whatever the tokens already name.
        current = [core[f"font.family.{s}"]["$value"] for s in ("display", "body", "mono")]
        return {slot: sorted(set(current)) for slot in ("display", "body", "mono")}

    families = sorted(json.loads(manifest.read_text())["families"])
    mono_first = sorted(families, key=lambda f: (not re.search(r"mono|code", f, re.I), f))
    return {"display": families, "body": families, "mono": mono_first}


# --------------------------------------------------------------------- Emit

WEIGHTS = {"Regular": 400, "Medium": 500, "Semi Bold": 600, "Bold": 700}
type_classes = []
for key in TYPE_ORDER:
    value = core[f"text.{key}"]["$value"]
    weight = WEIGHTS[core[ref_target(value["fontWeight"])]["$value"]]
    rules = [
        f"font-family: var({var_name(ref_target(value['fontFamily']))}), sans-serif",
        f"font-size: var({var_name(ref_target(value['fontSize']))})",
        f"font-weight: {weight}",
        f"line-height: var({var_name(ref_target(value['lineHeight']))})",
        f"letter-spacing: var({var_name(ref_target(value['letterSpacing']))})",
    ]
    if value.get("textCase") == "uppercase":
        rules.append("text-transform: uppercase")
    type_classes.append(".text-" + key + " {\n  " + ";\n  ".join(rules) + ";\n}")
TYPE_CLASSES = "\n".join(type_classes)

template = (ROOT / "preview.template.html").read_text()

# Embedded so the customise panel can regenerate and export the whole file set
# in the browser. textStyleSlots records which font family slot each text style
# used, so a font swap can be applied to the generated Figma styles too.
payload = {
    "files": {
        "core.json": json.loads((ROOT / "core.json").read_text()),
        "semantic/light.json": json.loads((ROOT / "semantic/light.json").read_text()),
        "semantic/dark.json": json.loads((ROOT / "semantic/dark.json").read_text()),
        "component.json": json.loads((ROOT / "component.json").read_text()),
        "figma-variables.json": json.loads((ROOT / "figma-variables.json").read_text()),
    },
    "brandSteps": [p.split(".")[-1] for p in core if p.startswith("color.brand.")],
    "brandRamp": {p.split(".")[-1]: core[p]["$value"] for p in core if p.startswith("color.brand.")},
    "fonts": {slot: core[f"font.family.{slot}"]["$value"] for slot in ("display", "body", "mono")},
    "textStyleSlots": [
        ref_target(core[f"text.{key}"]["$value"]["fontFamily"]).split(".")[-1]
        for key in TYPE_ORDER
    ],
    "families": available_families(),
}

html = (template
        .replace("/*PRIMITIVES*/", primitive_css)
        .replace("/*LIGHT*/", light_css)
        .replace("/*DARK*/", dark_css)
        .replace("/*COMPONENT*/", component_css)
        .replace("/*TYPESCALE*/", TYPE_CLASSES)
        .replace("<!--NAV-->", nav)
        .replace("<!--BODY-->", body)
        .replace("/*TOKENDATA*/", json.dumps(payload, separators=(",", ":"))))

out = ROOT / "preview.html"
out.write_text(html)
print(f"Wrote {out.name}  ({len(html) // 1024} KB, {len(SECTIONS)} sections)")

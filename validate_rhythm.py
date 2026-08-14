"""
Rhythm invariant checks for the token build.

Wire into build.py AFTER the flatten() calls near line 52:

    from validate_rhythm import check_rhythm
    check_rhythm(core, component)

It takes build.py's already-flattened dicts ({dotted.path: token}) and
resolves {alias} references itself, because build.py never computes
numeric values — resolve_alias() emits Figma alias pointers, not numbers.

The line-height map stays hand-authored. No formula reproduces it:
a single ratio plus snap-to-micro pushes 18px to 24 when it wants 28,
and tightening the ratio for display sizes breaks the small end instead.
Authoring the map and asserting the invariants gives the same safety
without the false precision.
"""

import re

BASE_UNIT = 24
MICRO_DIVISOR = 6
MICRO = BASE_UNIT // MICRO_DIVISOR  # 4

REF = re.compile(r"^\{([^}]+)\}$")


class RhythmError(AssertionError):
    pass


def _resolve(path, tokens, seen=None):
    """Follow {alias} chains until a number falls out. None if it can't."""
    seen = seen or set()
    if path in seen:
        raise RhythmError(f"circular reference at {path}")
    token = tokens.get(path)
    if token is None:
        return None
    value = token.get("$value")
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        match = REF.match(value.strip())
        if match:
            return _resolve(match.group(1), tokens, seen | {path})
    return None


def check_rhythm(core, component=None):
    """core and component are build.py's flattened {dotted.path: token} dicts."""
    errors = []
    tokens = dict(core)
    if component:
        tokens.update(component)

    if BASE_UNIT % MICRO_DIVISOR:
        errors.append(
            f"base unit {BASE_UNIT} is not divisible by micro divisor "
            f"{MICRO_DIVISOR} - micro unit would be fractional"
        )

    def value_of(path):
        try:
            return _resolve(path, tokens)
        except RhythmError as exc:
            errors.append(str(exc))
            return None

    # 1. every line-height sits on the micro unit
    lh_paths = [p for p in core if p.startswith("font.lineHeight.")]
    if not lh_paths:
        errors.append("no font.lineHeight.* tokens found - rhythm is undefined")

    line_heights = {}
    for path in lh_paths:
        value = value_of(path)
        if value is None:
            errors.append(f"{path} does not resolve to a number")
            continue
        line_heights[path] = value
        if value % MICRO:
            errors.append(f"{path} = {value} is not a multiple of the micro unit ({MICRO})")

    # 2. line-height + space-after resolves to a whole rhythm unit
    for path, lh in line_heights.items():
        key = path.rsplit(".", 1)[-1]
        after_path = f"font.spaceAfter.{key}"
        after = value_of(after_path)
        if after is None:
            errors.append(f"{after_path} missing - block total for {key} cannot be verified")
            continue
        block = lh + after
        if block % BASE_UNIT:
            errors.append(
                f"{key}: line-height {lh} + space-after {after} = {block}, "
                f"not a multiple of {BASE_UNIT}"
            )

    # 3. the rhythm group really is on rhythm
    for path in [p for p in core if p.startswith("rhythm.")]:
        value = value_of(path)
        if value is None:
            errors.append(f"{path} does not resolve to a number")
        elif value % BASE_UNIT:
            errors.append(
                f"{path} = {value} is in the rhythm group but is not a multiple of {BASE_UNIT}"
            )

    # 4. the grid row equals the body line-height
    body = line_heights.get("font.lineHeight.md")
    row = value_of("grid.row") if "grid.row" in tokens else None
    if row is not None and body is not None and row != body:
        errors.append(f"grid.row ({row}) has drifted from font.lineHeight.md ({body})")

    # 5. vertical layout tokens must not reach for micro-tier values
    for path in ("layout.page-padding-y", "layout.section-gap"):
        if path not in tokens:
            continue
        value = value_of(path)
        if value is not None and value % BASE_UNIT:
            errors.append(
                f"{path} = {value} is a vertical layout token but is not "
                f"a multiple of {BASE_UNIT} ({value / BASE_UNIT:.2f}u)"
            )

    if errors:
        raise RhythmError("rhythm invariants violated:\n  - " + "\n  - ".join(errors))

    return {
        "base_unit": BASE_UNIT,
        "micro_unit": MICRO,
        "line_heights_checked": len(line_heights),
    }

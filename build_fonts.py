#!/usr/bin/env python3
"""
Generate fonts/fonts.css from whatever font files are sitting in fonts/.

    python3 build_fonts.py           # scan fonts/ and write the CSS
    python3 build_fonts.py --npm     # first copy woff2 subsets from node_modules

Accepts .woff2, .woff, .ttf and .otf, so files downloaded straight from Google
Fonts (which ship as .ttf) work without conversion. Family and weight are read
from the filename — both the fontsource pattern (inter-latin-400-normal.woff2)
and the Google pattern (Inter-SemiBold.ttf, InterTight-VariableFont_wght.ttf).

Also writes fonts/fonts.json, which the preview reads to populate its font
dropdowns — so the picker only ever offers families you actually have.
"""

import json
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
FONTS = ROOT / "fonts"

EXTENSIONS = {".woff2": "woff2", ".woff": "woff", ".ttf": "truetype", ".otf": "opentype"}
# woff2 first — browsers pick the first format they support.
PRIORITY = {"woff2": 0, "woff": 1, "truetype": 2, "opentype": 3}

# Keyed on the filename stripped to lowercase letters and digits, so the same
# entry catches "JetBrainsMono-Bold.ttf" and "jetbrains-mono-latin-700-normal.woff2".
KNOWN_FAMILIES = {
    "inter": "Inter",
    "intertight": "Inter Tight",
    "jetbrainsmono": "JetBrains Mono",
    "spacegrotesk": "Space Grotesk",
    "sourceserif4": "Source Serif 4",
    "sourceserifpro": "Source Serif Pro",
    "ibmplexsans": "IBM Plex Sans",
    "ibmplexmono": "IBM Plex Mono",
    "ibmplexserif": "IBM Plex Serif",
    "robotomono": "Roboto Mono",
    "sourcesans3": "Source Sans 3",
}

WEIGHT_NAMES = {
    "thin": 100, "extralight": 200, "ultralight": 200, "light": 300,
    "regular": 400, "normal": 400, "book": 400, "medium": 500,
    "semibold": 600, "demibold": 600, "bold": 700,
    "extrabold": 800, "ultrabold": 800, "black": 900, "heavy": 900,
}

FONTSOURCE = re.compile(r"^(?P<family>.+?)-(?:latin|latin-ext)-(?P<weight>\d{3})-(?P<style>normal|italic)$")


def canonical(raw):
    key = re.sub(r"[^a-z0-9]", "", raw.lower())
    if key in KNOWN_FAMILIES:
        return KNOWN_FAMILIES[key]
    # Fall back to splitting CamelCase, keeping acronyms together.
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", raw)
    return spaced.replace("-", " ").replace("_", " ").strip().title() \
        if spaced.islower() else spaced.replace("-", " ").replace("_", " ").strip()


def parse(path):
    """Filename -> {family, weight, style} or None if it can't be read."""
    fmt = EXTENSIONS.get(path.suffix.lower())
    if fmt is None:
        return None
    stem = path.stem

    match = FONTSOURCE.match(stem)
    if match:
        return {
            "family": canonical(match.group("family")),
            "weight": str(int(match.group("weight"))),
            "style": match.group("style"),
            "format": fmt,
        }

    stem = re.sub(r"_\d+pt", "", stem)          # Inter_18pt-Regular -> Inter-Regular
    stem = re.sub(r"\[.*?\]", "", stem)          # Inter[opsz,wght] -> Inter
    family_part, _, style_part = stem.rpartition("-")
    if not family_part:
        family_part, style_part = stem, "Regular"

    italic = "italic" in style_part.lower()

    if "variablefont" in style_part.lower().replace(" ", "") or "wght" in style_part.lower():
        weight = "100 900"   # variable font: declare the full axis range
    else:
        key = re.sub(r"[^a-z]", "", style_part.lower().replace("italic", ""))
        if not key:
            key = "regular"   # "Inter-Italic.ttf" is regular weight, italic style
        if key not in WEIGHT_NAMES:
            return None
        weight = str(WEIGHT_NAMES[key])

    return {
        "family": canonical(family_part),
        "weight": weight,
        "style": "italic" if italic else "normal",
        "format": fmt,
    }


def copy_from_npm():
    modules = ROOT / "node_modules" / "@fontsource"
    if not modules.exists():
        raise SystemExit(
            "node_modules/@fontsource not found. Run:\n"
            "  npm install @fontsource/inter @fontsource/inter-tight "
            "@fontsource/jetbrains-mono @fontsource/space-grotesk "
            "@fontsource/source-serif-4 @fontsource/ibm-plex-sans @fontsource/ibm-plex-mono"
        )
    FONTS.mkdir(exist_ok=True)
    copied = 0
    for package in sorted(modules.iterdir()):
        files = package / "files"
        if not files.is_dir():
            continue
        for src in files.glob(f"*-latin-*-normal.woff2"):
            if int(src.stem.split("-")[-2]) in (400, 500, 600, 700):
                shutil.copy(src, FONTS / src.name)
                copied += 1
    print(f"Copied {copied} woff2 files from node_modules")


def main():
    if "--npm" in sys.argv:
        copy_from_npm()

    if not FONTS.is_dir():
        raise SystemExit(f"No fonts/ directory at {FONTS}. Create it and add font files.")

    # Group so one @font-face can list several formats for the same face.
    faces = defaultdict(list)
    unreadable = []
    for path in sorted(FONTS.iterdir()):
        if path.suffix.lower() not in EXTENSIONS:
            continue
        info = parse(path)
        if info is None:
            unreadable.append(path.name)
            continue
        faces[(info["family"], info["weight"], info["style"])].append((info["format"], path.name))

    if not faces:
        raise SystemExit(
            "No readable font files in fonts/.\n"
            "Expected names like 'Inter-Regular.ttf' or 'inter-latin-400-normal.woff2'."
        )

    rules = [
        "/* Generated by build_fonts.py — do not edit by hand.",
        " * Regenerate after adding or removing files in this folder. */",
        "",
    ]
    for (family, weight, style), sources in sorted(faces.items()):
        sources.sort(key=lambda s: PRIORITY[s[0]])
        src = ",\n       ".join(f"url('./{name}') format('{fmt}')" for fmt, name in sources)
        rules.append(
            "@font-face {\n"
            f"  font-family: '{family}';\n"
            f"  font-style: {style};\n"
            f"  font-weight: {weight};\n"
            "  font-display: swap;\n"
            f"  src: {src};\n"
            "}\n"
        )
    (FONTS / "fonts.css").write_text("\n".join(rules))

    # Manifest for the preview's font pickers.
    manifest = defaultdict(lambda: {"weights": set(), "italic": False})
    for (family, weight, style) in faces:
        if style == "italic":
            manifest[family]["italic"] = True
        else:
            manifest[family]["weights"].add(weight)
    families = {
        family: {"weights": sorted(info["weights"], key=lambda w: (len(w), w)), "italic": info["italic"]}
        for family, info in sorted(manifest.items())
    }
    (FONTS / "fonts.json").write_text(json.dumps({"families": families}, indent=2) + "\n")

    print(f"Wrote fonts/fonts.css — {len(faces)} faces across {len(families)} families:")
    for family, info in families.items():
        print(f"  {family:20s} {', '.join(info['weights'])}")

    overlapping = [f for f, i in families.items()
                   if any(" " in w for w in i["weights"]) and len(i["weights"]) > 1]
    if overlapping:
        print("\nBoth a variable font and static weights are present for: "
              + ", ".join(overlapping))
        print("Their weight ranges overlap. Keep one set to avoid ambiguity.")

    if unreadable:
        print(f"\nCouldn't read a weight from {len(unreadable)} file(s); they were skipped:")
        for name in unreadable:
            print(f"  {name}")
        print("Rename them like 'Family-Weight.ttf', e.g. Inter-SemiBold.ttf.")


if __name__ == "__main__":
    main()

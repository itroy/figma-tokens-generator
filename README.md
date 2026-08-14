# Design token system

A three-tier token system that imports into Figma as native variables, using a small
MIT-style importer plugin maintained in its own repo:
[itroy/figma-tokens-plugin](https://github.com/itroy/figma-tokens-plugin).

This repo owns the token source and `build.py`, which compiles it down to
`figma-variables.json` — that file is the handoff point. The plugin repo consumes it and
knows nothing about `core.json`, `semantic/*.json`, or `component.json`; everything it
needs to build Figma variables, text styles, and effect styles is already resolved into
that one JSON file.

___

#### Code TODO:
- [ ] Create repo on GitHub
- [ ] build_fonts.py to file fonts into folders
- [ ] Documentation

#### Figma TODO:
- [ ] Test Token Plugin System
- [ ] Test flexibility (can Tokens live in one file and populate another - what to do in terms of creating seperate design systems)

---

#### Open Questions:
1. Should / Could this edit functionality all live inside the Figma plugin? With Preview / Setup / Editable decision screens?


```
design-tokens/
├── core.json               primitives — palettes, scales, type
├── semantic/
│   ├── light.json          role tokens, light mode
│   └── dark.json           role tokens, dark mode
├── component.json          component-level tokens
├── build.py                compiles the above into ↓
├── figma-variables.json    generated — this is what you import
├── preview.py              generates ↓ from the same token source
├── preview.template.html   the preview's shell and styling
├── preview.html            generated
├── serve.py                local server — run the preview through this
├── build_fonts.py          generates fonts/fonts.css from the files in fonts/
└── fonts/                  self-hosted font files + fonts.css + fonts.json
```

## Fonts

`fonts/` must contain the font files **and** a generated `fonts.css`. If the folder is
missing or incomplete, the preview shows an orange banner at the top saying so, and falls
back to system fonts.

To add or replace fonts, drop the files in `fonts/` and run:

```bash
python3 build_fonts.py
```

It accepts `.woff2`, `.woff`, `.ttf` and `.otf`, so files downloaded straight from Google
Fonts work without conversion. Family and weight are read from the filename — both the
Google pattern (`Inter-SemiBold.ttf`, `InterTight-VariableFont_wght.ttf`) and the
fontsource pattern (`inter-latin-400-normal.woff2`). Anything it can't read is listed at
the end of the run rather than dropped quietly, and it warns if a family has both a
variable font and static weights, since their ranges overlap.

The script also writes `fonts/fonts.json`, which the preview reads to populate its font
dropdowns — so the picker only ever offers families you actually have.

`.woff2` is worth preferring over the `.ttf` Google hands you: roughly a third of the size
for identical rendering. To re-fetch the bundled set:

```bash
npm install @fontsource/inter @fontsource/inter-tight @fontsource/jetbrains-mono \
            @fontsource/space-grotesk @fontsource/source-serif-4 \
            @fontsource/ibm-plex-sans @fontsource/ibm-plex-mono
python3 build_fonts.py --npm
```

## Preview the system

```bash
python3 serve.py
```

Then open <http://127.0.0.1:8000/preview.html>.

**Use the server rather than opening the file directly.** Browsers give `file://` pages an
opaque origin, and `@font-face` requests from an opaque origin get blocked — so the
specimen silently falls back to system fonts and the type is misrepresented. This is a
browser security rule, not something the page can opt out of. Serving over http fixes it.
The fonts themselves are vendored into `fonts/`, so nothing is fetched from a CDN and the
page works offline.

The page has a sidebar, a light/dark switch, and a section per layer — brand first, then
semantic colour, typography, spacing, shape, elevation, components, and primitives last.
Every value is generated from the same JSON the plugin imports, so the preview can't drift
from what's in Figma. Semantic swatches show their full resolution chain
(`bg/surface → color/neutral/0 → #FFFFFF`), and the chain re-resolves live when you flip
modes — that's the alias structure working, not a second set of colours. Click any token
name to copy its CSS variable.

## Customising from the preview

Open **Customise** in the sidebar to change the brand colour and the three font families,
then take the result away as files.

**Brand colour.** Pick a hex and the whole eleven-step ramp re-derives in OKLCH. The new
hue and chroma are adopted, but each step keeps the *lightness* of the step it replaces.
That matters: lightness is what drives contrast, so the AA guarantees below survive a
rebrand instead of quietly breaking. Chroma is reduced per step where a hue can't reach it
in sRGB, so no step clips. The panel shows live contrast for the pairings the ramp actually
creates — white on the primary button in both modes, and link text on the dark canvas —
and warns if any drops below 4.5:1.

**Fonts.** The dropdowns list whatever families `build_fonts.py` found in `fonts/`. Add
more by dropping files in that folder and re-running it.

**Export.** Two ways out:

- **Export .zip** downloads `core.json`, both semantic files, `component.json`, and
  `figma-variables.json` with your edits applied. Unzip over this folder. Works from
  anywhere, including a plain file open.
- **Save to project** (only shown when served) POSTs to `serve.py`, which rewrites
  `core.json` and re-runs both generators. Reload to see the regenerated page. The server
  binds to `127.0.0.1` only and validates every value before writing.

Either way the semantic and component layers are untouched — they alias `{color.brand.600}`
by name, so a rebrand needs no edits below the primitive layer. That is the whole point of
the three tiers, and the export is a decent demonstration of it.

## Import into Figma

The importer plugin lives in a separate repo:
[itroy/figma-tokens-plugin](https://github.com/itroy/figma-tokens-plugin). Clone it
alongside this one.

1. Open the Figma **desktop app** (local plugins don't run in the browser).
2. Menu → **Plugins → Development → Import plugin from manifest…** and select
   `manifest.json` from the plugin repo. You only do this once.
3. Open the file you want the variables in, then **Plugins → Development → Token Importer**.
4. Drop this repo's `figma-variables.json` onto the window and hit **Import**.

You'll get three collections — `Primitives`, `Semantic` (with Light and Dark modes),
and `Component` — plus 12 text styles and 6 effect styles. 283 variables in total.

Re-running the plugin **updates in place** rather than duplicating: it matches on
collection and variable name, so editing a token and re-importing does what you'd hope.

## Editing tokens

Edit the source JSON, then regenerate:

```bash
python3 build.py      # regenerate figma-variables.json
python3 preview.py    # regenerate preview.html
```

The build prints what it wrote and, importantly, what it *couldn't* carry across.
Don't hand-edit `figma-variables.json` or `preview.html` — both get overwritten.

## The three tiers

**Core** holds raw values and no opinions. `color.brand.600` describes a colour, not a
job. Nothing in your designs should point at this layer directly.

**Semantic** assigns jobs: `bg.surface`, `fg.muted`, `action.primary.bg-hover`. Both mode
files declare the *same token names* with different values — that's what becomes the two
modes of the Semantic collection. If you add a token to one file, add it to the other or
the build will stop and tell you which one is missing.

**Component** composes semantic tokens into per-component decisions: `button.md.padding-x`,
`card.radius`, `modal.scrim`. It aliases the Semantic collection, so component variables
follow whichever mode a frame is set to without needing modes of their own.

The payoff: rebranding touches `core`, retheming touches `semantic`, and component tweaks
stay contained. In Figma this shows up as a real alias chain — `Component/card/bg` →
`Semantic/bg/surface` → `Primitives/color/neutral/0` — so you can trace any value back to
its source in the variable picker.

## What crosses over, and what doesn't

Figma variables only hold colours, numbers, strings, and booleans. The build handles the
gaps rather than silently dropping things:

| Source | Becomes |
|---|---|
| Colours | Colour variables, scoped to fills / strokes / text as appropriate |
| Spacing, sizing, radius, border width, font size | Number variables, scoped to the matching property |
| Font families and weights | String variables |
| `text.*` composites | **Text styles** — Figma has no typography variable type |
| `elevation.*` shadows | **Effect styles**, one set per mode (`Elevation/Light/…`, `Elevation/Dark/…`) |
| Line height, letter spacing | Baked into the text styles — they're percentages, and variables only take absolute numbers |
| Duration, easing | Not imported; they exist for code export only |

Effect styles don't respond to variable modes, which is a Figma limitation rather than a
choice here — hence the separate Light and Dark elevation sets. Swap the style when you
swap the mode.

Each variable also gets a **web code syntax** value (`--bg-canvas`, `--space-4`) so Dev
Mode shows the CSS custom property name your engineers will actually use.

## Plan limits worth knowing

- **Starter (free)** allows one mode per collection. The plugin detects this, imports
  Light, and tells you Dark was skipped rather than failing halfway. Everything else
  imports normally.
- **Professional and Organization** allow four modes — plenty for Light and Dark.
- The **Variables REST API is Enterprise-only**, which is why this uses a plugin. If you
  ever land on Enterprise, `figma-variables.json` maps closely onto the REST payload and
  can drive CI sync instead.

Figma also ships an [official open-source sample](https://github.com/figma/plugin-samples/tree/master/variables-import-export)
for variable import/export. It's a reasonable fallback, but it doesn't handle multiple
modes, alias chains across collections, scopes, or styles — which is most of the work here.

## Type

The scale pairs **Inter Tight** for display and headings with **Inter** for body, plus
**JetBrains Mono** for code. The preview self-hosts these; Figma needs them installed
locally, and if one is missing the plugin falls back to Inter Regular and says so in the
report rather than erroring out.

To swap faces, use the preview's Customise panel or edit `font.family` in `core.json`.
One gotcha either way: `font.weight` holds *Figma style names*, and different families
name their weights differently — Figma calls Inter's semibold "Semi Bold" with a space,
while some families use "SemiBold". If text styles import at the wrong weight, that
mismatch is why.

## Accessibility

Every foreground/background pairing in the semantic layer clears WCAG AA (4.5:1) for body
text against its intended surface, in both modes. The tightest are `fg.subtle` on
`bg.muted` (4.51:1) and `action.primary` in dark mode (4.85:1) — if you shift
`neutral.500` or `brand.500`, re-check those two first.

`focus.ring` is a dedicated token rather than a reuse of `border.brand`, so you can
strengthen focus visibility without touching brand colour.

## Extending it

- **New brand colour**: replace the eleven steps of `color.brand` in `core.json`. Keep
  step 600 as the light-mode solid and 500 as the dark-mode solid and the semantic layer
  keeps working.
- **A third mode** (high contrast, a sub-brand): add a `semantic/contrast.json` with
  identical token names, then add it to the `Semantic` collection's mode list in
  `build.py`. Needs Professional or above.
- **A new component**: add a group to `component.json` referencing semantic tokens only.
  If you find yourself reaching for `{color.*}` there, the semantic layer is probably
  missing a role.

## Exporting to code

The source files are plain DTCG (`$value` / `$type`), so [Style Dictionary](https://styledictionary.com)
can consume them directly to produce CSS custom properties, Tailwind config, iOS, or
Android output. Keep Figma and code building from this one source rather than maintaining
parallel copies.

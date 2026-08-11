#!/usr/bin/env python3
"""
Serve the token folder on localhost.

    python3 serve.py            # http://127.0.0.1:8000/preview.html
    python3 serve.py 8080       # pick a port

Two reasons this exists rather than opening preview.html directly:

1. Browsers give file:// pages an opaque origin, and @font-face requests from
   an opaque origin get blocked — so the specimen falls back to system fonts.
   Serving over http fixes it, including for the locally vendored woff2 files.
2. It accepts a save from the preview's customise panel, rewriting core.json
   and regenerating both build outputs, so you can iterate without leaving
   the browser.

Binds to 127.0.0.1 only. It writes to the token files in this folder — that's
the point of it — but it will not touch anything outside them.
"""

import json
import re
import subprocess
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
FAMILY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .\-]{0,39}$")
BRAND_STEPS = ["50", "100", "200", "300", "400", "500", "600", "700", "800", "900", "950"]

# The only paths a save is ever allowed to touch.
ALLOWED_FILES = {
    "core.json",
    "semantic/light.json",
    "semantic/dark.json",
    "component.json",
    "figma-variables.json",
}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):
        if "/api/" in (self.path or "") or self.command != "GET":
            sys.stderr.write("  %s %s\n" % (self.command, self.path))

    def end_headers(self):
        # No caching, so a regenerated preview.html shows up on reload.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_POST(self):
        if self.path != "/api/save":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 200_000:
                raise ValueError("payload too large")
            payload = json.loads(self.rfile.read(length))
            summary = save(payload)
        except Exception as err:
            self.respond(400, {"ok": False, "error": str(err)})
            return
        self.respond(200, {"ok": True, **summary})

    def respond(self, status, body):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def save(payload):
    """Write the token files the preview sends us, then regenerate.

    The browser already holds the full patched set — it is the same content
    Export .zip produces. Taking it wholesale means Save works even in a folder
    that is missing the JSON sources, and guarantees the two export paths can't
    drift apart.
    """
    files = payload.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("no files in request")

    unexpected = sorted(set(files) - ALLOWED_FILES)
    if unexpected:
        raise ValueError(f"refusing to write unexpected file(s): {', '.join(unexpected)}")

    # Parse everything before writing anything, so a bad payload can't leave
    # the folder half-updated.
    parsed = {}
    for name, content in files.items():
        if not isinstance(content, str) or len(content) > 2_000_000:
            raise ValueError(f"bad content for {name}")
        try:
            parsed[name] = json.loads(content)
        except json.JSONDecodeError as err:
            raise ValueError(f"{name} is not valid JSON: {err}") from None

    core = parsed.get("core.json")
    if core is not None:
        brand = core.get("color", {}).get("brand", {})
        for step in BRAND_STEPS:
            value = brand.get(step, {}).get("$value")
            if not HEX.match(str(value)):
                raise ValueError(f"bad brand value at step {step}: {value!r}")
        for slot in ("display", "body", "mono"):
            family = core.get("font", {}).get("family", {}).get(slot, {}).get("$value")
            if not FAMILY.match(str(family)):
                raise ValueError(f"bad font family for {slot}: {family!r}")

    written = []
    for name, content in files.items():
        target = (ROOT / name).resolve()
        if not str(target).startswith(str(ROOT) + "/"):
            raise ValueError(f"path escapes the token folder: {name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        written.append(name)

    # Regenerating is a nicety — say so plainly if the scripts aren't here.
    rebuilt, skipped = [], []
    for script in ("build.py", "preview.py"):
        if not (ROOT / script).exists():
            skipped.append(script)
            continue
        result = subprocess.run(
            [sys.executable, script], cwd=ROOT, capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"{script} failed: {result.stderr.strip()[:300]}")
        rebuilt.append(result.stdout.strip().splitlines()[0])

    return {"written": sorted(written), "rebuilt": rebuilt, "skipped": skipped}


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Serving {ROOT}")
    print(f"  http://127.0.0.1:{port}/preview.html")

    expected = sorted(ALLOWED_FILES) + ["build.py", "preview.py", "preview.html", "fonts/fonts.css"]
    missing = [name for name in expected if not (ROOT / name).exists()]
    if missing:
        print("\nMissing from this folder:")
        for name in missing:
            print(f"  {name}")
        print("The preview still runs, and Save to project will write the token files")
        print("it sends. Regenerating needs build.py and preview.py to be present.")

    print("\nCtrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()

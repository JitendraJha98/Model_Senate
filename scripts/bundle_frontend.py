"""Build the frontend and copy it into backend/static so it ships inside the wheel.

Run before a release build:

    python scripts/bundle_frontend.py
    uv build            # produces dist/*.whl with the UI bundled in
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
STATIC = ROOT / "backend" / "static"


def main() -> None:
    npm = "npm.cmd" if os.name == "nt" else "npm"
    if shutil.which(npm) is None:
        sys.exit("npm not found on PATH — install Node.js first.")

    subprocess.run([npm, "install"], cwd=FRONTEND, check=True)
    subprocess.run([npm, "run", "build"], cwd=FRONTEND, check=True)

    dist = FRONTEND / "dist"
    if not (dist / "index.html").exists():
        sys.exit(f"Frontend build did not produce {dist / 'index.html'}")

    if STATIC.exists():
        shutil.rmtree(STATIC)
    shutil.copytree(dist, STATIC)
    print(f"Bundled frontend: {dist} -> {STATIC}")


if __name__ == "__main__":
    main()

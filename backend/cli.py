"""Console entry point: `model-senate` launches the API + bundled UI in one command."""
from __future__ import annotations

import argparse
import threading
import webbrowser

import uvicorn

from backend.config import get_settings


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        prog="model-senate",
        description="Run one prompt through multiple AI models and synthesize a researched answer.",
    )
    parser.add_argument("--host", default=settings.model_senate_host, help="Bind host")
    parser.add_argument("--port", type=int, default=settings.model_senate_port, help="Bind port")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (development)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser window")
    args = parser.parse_args()

    display_host = "localhost" if args.host in {"0.0.0.0", "127.0.0.1"} else args.host
    url = f"http://{display_host}:{args.port}"
    print(f"\n  🏛️  Model Senate is starting at {url}\n")

    if not args.no_browser:
        # Give uvicorn a moment to bind before opening the browser.
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    uvicorn.run("backend.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()

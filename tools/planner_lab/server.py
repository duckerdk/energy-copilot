"""Optional local server for Planner Lab; GitHub Pages uses engine.py in Pyodide."""

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

if __package__:
    from .engine import _core_modules, simulate_scenario
else:
    from engine import _core_modules, simulate_scenario

MAX_BODY_BYTES = 160_000


class Handler(BaseHTTPRequestHandler):
    def _reply(self, code, content, media_type):
        self.send_response(code)
        self.send_header("Content-Type", media_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        static = {
            "/": (Path(__file__).parent / "index.html", "text/html; charset=utf-8"),
            "/index.html": (Path(__file__).parent / "index.html", "text/html; charset=utf-8"),
            "/worker.js": (Path(__file__).parent / "worker.js", "text/javascript; charset=utf-8"),
            "/engine.py": (Path(__file__).parent / "engine.py", "text/plain; charset=utf-8"),
            "/planner.py": (
                Path(__file__).resolve().parents[2]
                / "custom_components"
                / "energy_copilot"
                / "planner.py",
                "text/plain; charset=utf-8",
            ),
            "/horizon_optimizer.py": (
                Path(__file__).resolve().parents[2]
                / "custom_components"
                / "energy_copilot"
                / "horizon_optimizer.py",
                "text/plain; charset=utf-8",
            ),
        }
        selected = static.get(self.path)
        if selected is None:
            return self._reply(404, b"Not found", "text/plain; charset=utf-8")
        path, media_type = selected
        return self._reply(200, path.read_bytes(), media_type)

    def do_POST(self):
        if self.path != "/api/simulate":
            return self._reply(404, b"Not found", "text/plain; charset=utf-8")
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY_BYTES:
                raise ValueError("Wielkość danych przekracza limit")
            request = json.loads(self.rfile.read(length))
            response = simulate_scenario(request)
            status = 200
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            response, status = {"error": str(exc)}, 400
        except Exception:
            # Do not expose server tracebacks to the browser.
            self.log_error("Unexpected simulation exception: %r", sys.exc_info()[1])
            response, status = {"error": "Wewnętrzny błąd symulacji. Sprawdź konsolę."}, 500
        data = json.dumps(response, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self._reply(status, data, "application/json; charset=utf-8")

    def log_message(self, fmt, *args):
        print(fmt % args, flush=True)


def main():
    parser = argparse.ArgumentParser(description="Offline Planner Lab - bez HA i falownika")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    _core_modules()
    address = f"http://127.0.0.1:{args.port}"
    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        print(f"Planner Lab: {address}\nZamknięcie: Ctrl+C", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()

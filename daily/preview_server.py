#!/usr/bin/env python3
"""No-cache local server for the generated preview bundle."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse
import os

class NoCacheHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        translated = Path(super().translate_path(path))
        if not translated.suffix and not translated.exists():
            html_path = translated.with_suffix(".html")
            if html_path.is_file():
                return str(html_path)
        return str(translated)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8799)
    args = parser.parse_args()
    os.chdir(args.root)
    ThreadingHTTPServer(("127.0.0.1", args.port), NoCacheHandler).serve_forever()

if __name__ == "__main__":
    main()

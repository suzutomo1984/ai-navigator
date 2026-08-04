"""Serve the project for local browser regression tests without caching assets."""

from argparse import ArgumentParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class NoCacheHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("--port", type=int, default=8799)
    parser.add_argument("--directory", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()

    handler = lambda *handler_args, **handler_kwargs: NoCacheHandler(  # noqa: E731
        *handler_args,
        directory=str(args.directory),
        **handler_kwargs,
    )
    ThreadingHTTPServer(("127.0.0.1", args.port), handler).serve_forever()


if __name__ == "__main__":
    main()

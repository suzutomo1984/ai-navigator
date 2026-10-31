"""Serve and rebuild the local article preview when a draft is saved."""
from datetime import datetime
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
import hashlib
import socket
import threading
import time
import webbrowser

import build_articles
from daily.preview_server import NoCacheHandler

ROOT = Path(__file__).resolve().parent


class PreviewServer(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR can allow another process to steal an occupied port.
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def create_server(start=8080):
    handler = partial(NoCacheHandler, directory=str(ROOT))
    for port in range(start, 65536):
        try:
            return PreviewServer(('127.0.0.1', port), handler)
        except OSError as exc:
            if exc.errno not in (48, 98, 10048):
                raise
    raise RuntimeError('空いているポートが見つかりません。')


def snapshot():
    result = {}
    for path in sorted((ROOT / 'posts').glob('*.md')):
        if not path.name.startswith('_'):
            try:
                result[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                result[path.name] = None
    return result


def rebuild(names):
    try:
        build_articles.build()
        titles = []
        for name in names:
            path = ROOT / 'posts' / name
            if path.exists():
                titles.append(build_articles.load_post(path)[0]['title'])
            else:
                titles.append(name + '（削除）')
        print(f'更新しました {datetime.now().strftime("%H:%M:%S")}（{ "、".join(titles) if titles else "記事一覧"}）', flush=True)
    except Exception as exc:
        print(f'記事を作り直せませんでした。前の HTML を残しました: {exc}', flush=True)


def main():
    server = create_server()
    port = server.server_address[1]
    before = snapshot()
    rebuild(list(before))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{port}/articles/'
    print(f'プレビュー: {url}', flush=True)
    try:
        if not webbrowser.open(url):
            print('ブラウザを開けませんでした。上の URL を開いてください。', flush=True)
    except webbrowser.Error as exc:
        print(f'ブラウザを開けませんでした。上の URL を開いてください: {exc}', flush=True)
    try:
        while True:
            time.sleep(1)
            current = snapshot()
            changed = sorted(name for name in before.keys() | current.keys() if before.get(name) != current.get(name))
            if changed:
                rebuild(changed)
                before = current
    except KeyboardInterrupt:
        print('\nプレビューを終了します。', flush=True)
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()

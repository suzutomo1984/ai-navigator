import json
import re
import shutil
from pathlib import Path
import sys
import socket
from datetime import date, timedelta
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_articles as builder
from preview_articles import create_server

ROOT = Path(__file__).resolve().parents[1]


def draft_posts(tmp_path):
    # Tests start from a draft copy so publishing the real post does not change them.
    shutil.copytree(ROOT / 'posts', tmp_path / 'posts')
    post = tmp_path / 'posts/bitwarden-to-1password.md'
    post.write_text(re.sub(r'(?m)^published:.*$', 'published:', post.read_text(encoding='utf-8')), encoding='utf-8')
    return post


def test_faq_and_json_and_unpublished(tmp_path):
    meta, body = builder.load_post(draft_posts(tmp_path))
    questions = builder.faq(body)
    assert len(questions) == 5
    assert questions[0]['name'] == 'パスキーはファイル取り込みで移りますか'
    page = builder.render_article(meta, body)
    data = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', page).group(1))
    assert [item['@type'] for item in data] == ['Article', 'FAQPage', 'BreadcrumbList']
    assert data[1]['mainEntity'] == questions
    assert 'datePublished' not in data[0]
    assert data[0]['dateModified'] == '2026-10-27'
    assert data[0]['author'] == {'@type':'Organization','name':'AI Navigator'}


def test_placeholder():
    assert builder.markdown('【画像: 画面の説明】') == '<figure class="placeholder">画像: 画面の説明</figure>'


def test_toc_links_only_to_body_h2():
    meta, body = builder.load_post(ROOT / 'posts/bitwarden-to-1password.md')
    page = builder.render_article(meta, body)
    toc = re.search(r'<details class="article-toc".*?</details>', page).group()
    links = re.findall(r'<a href="#(sec-\d+)">(.*?)</a>', toc)
    h2 = re.findall(r'<h2 id="(sec-\d+)">(.*?)</h2>', page)
    assert len(links) == len(h2) == 9
    assert links == h2
    assert all(page.count(f'id="{ident}"') == 1 for ident, _ in links)
    assert all(title not in toc for title in re.findall(r'<h3>(.*?)</h3>', page))
    assert page.index('</aside>') < page.index('<details class="article-toc"') < page.index('<h2 id="sec-1">')


def test_repeated_headings_have_unique_links():
    meta, _ = builder.load_post(ROOT / 'posts/bitwarden-to-1password.md')
    page = builder.render_article(meta, '## 同じ見出し\n本文\n\n## 同じ見出し\n本文')
    assert re.findall(r'<h2 id="(sec-\d+)">', page) == ['sec-1', 'sec-2']
    assert re.findall(r'href="#(sec-\d+)"', page) == ['sec-1', 'sec-2']


def test_build_twice_is_idempotent(tmp_path):
    draft_posts(tmp_path)
    post = tmp_path / 'posts/bitwarden-to-1password.md'
    post.write_text(post.read_text(encoding='utf-8').replace('published:\n', 'published: 2026-10-30\n'), encoding='utf-8')
    for name in ('sitemap.xml', 'llms.txt'):
        shutil.copy(ROOT / name, tmp_path / name)
    builder.build(tmp_path, publish=True, today=date(2026, 10, 31))
    before = {name: (tmp_path / name).read_text(encoding='utf-8') for name in ('sitemap.xml', 'llms.txt')}
    builder.build(tmp_path, publish=True, today=date(2026, 10, 31))
    for name, text in before.items():
        assert (tmp_path / name).read_text(encoding='utf-8') == text
        assert text.count('https://ai-navigator.dev/articles/bitwarden-to-1password') == 1
    assert before['sitemap.xml'].count('<loc>https://ai-navigator.dev/articles/</loc>') == 1


def test_preview_drafts_and_publish_cleanup(tmp_path):
    draft_posts(tmp_path)
    for name in ('sitemap.xml', 'llms.txt'):
        shutil.copy(ROOT / name, tmp_path / name)
    today = date(2026, 10, 31)
    draft = tmp_path / 'posts/bitwarden-to-1password.md'
    text = draft.read_text(encoding='utf-8')
    future = text.replace('slug: bitwarden-to-1password', 'slug: future').replace('published:\n', f'published: {today + timedelta(days=1)}\n')
    (tmp_path / 'posts/future.md').write_text(future, encoding='utf-8')
    (tmp_path / 'posts/_bad.md').write_text('not valid', encoding='utf-8')
    before = {name: (tmp_path / name).read_bytes() for name in ('sitemap.xml', 'llms.txt')}
    builder.build(tmp_path, today=today)
    for name in ('bitwarden-to-1password', 'future'):
        page = (tmp_path / 'articles' / (name+'.html')).read_text(encoding='utf-8')
        assert '下書き（公開前）・このページは本番に出ません' in page
        assert '<meta name="robots" content="noindex">' in page
    index = (tmp_path / 'articles/index.html').read_text(encoding='utf-8')
    assert index.count('class="draft-badge"') == 2
    assert all((tmp_path / name).read_bytes() == value for name, value in before.items())
    (tmp_path / 'articles/stale.html').write_text('old', encoding='utf-8')
    builder.build(tmp_path, publish=True, today=today)
    assert sorted(p.name for p in (tmp_path / 'articles').glob('*.html')) == ['index.html']
    assert 'class="draft-badge"' not in (tmp_path / 'articles/index.html').read_text(encoding='utf-8')
    assert 'https://ai-navigator.dev/articles/future' not in (tmp_path / 'sitemap.xml').read_text(encoding='utf-8')
    assert 'https://ai-navigator.dev/articles/bitwarden-to-1password' not in (tmp_path / 'llms.txt').read_text(encoding='utf-8')


def test_publish_today_and_validation_preserves_html(tmp_path):
    draft_posts(tmp_path)
    for name in ('sitemap.xml', 'llms.txt'):
        shutil.copy(ROOT / name, tmp_path / name)
    post = tmp_path / 'posts/bitwarden-to-1password.md'
    text = post.read_text(encoding='utf-8').replace('published:\n', 'published: 2026-10-31\n')
    post.write_text(text, encoding='utf-8')
    builder.build(tmp_path, publish=True, today=date(2026, 10, 31))
    page = tmp_path / 'articles/bitwarden-to-1password.html'
    before = page.read_bytes()
    assert b'noindex' not in before
    post.write_text(text.replace('checked: 2026-10-27', 'checked: wrong-date'), encoding='utf-8')
    with pytest.raises(builder.PostError, match=r'bitwarden-to-1password.md の 8 行目'):
        builder.build(tmp_path, today=date(2026, 10, 31))
    assert page.read_bytes() == before


def test_image_markup():
    assert '<img src="https://example.com/a.jpg" alt="説明">' in builder.markdown('![説明](https://example.com/a.jpg)')


def test_busy_port_is_not_reused():
    with socket.socket() as occupied:
        occupied.bind(('127.0.0.1', 0))
        occupied.listen()
        port = occupied.getsockname()[1]
        server = create_server(port)
        try:
            assert server.server_address[1] > port
        finally:
            server.server_close()


def test_publish_after_sitemap_generation(tmp_path, monkeypatch):
    import parse_news
    draft_posts(tmp_path)
    shutil.copy(ROOT / 'llms.txt', tmp_path / 'llms.txt')
    post = tmp_path / 'posts/bitwarden-to-1password.md'
    post.write_text(post.read_text(encoding='utf-8').replace('published:\n', 'published: 2026-10-30\n'), encoding='utf-8')
    monkeypatch.setattr(parse_news, 'SITEMAP_FILE', tmp_path / 'sitemap.xml')
    parse_news.generate_sitemap(editions_path=tmp_path / 'missing.json')
    builder.build(tmp_path, publish=True, today=date(2026, 10, 31))
    sitemap = (tmp_path / 'sitemap.xml').read_text(encoding='utf-8')
    assert '<loc>https://ai-navigator.dev/news</loc>' in sitemap
    assert sitemap.count('<loc>https://ai-navigator.dev/articles/bitwarden-to-1password</loc>') == 1
    assert (tmp_path / 'articles/bitwarden-to-1password.html').exists()

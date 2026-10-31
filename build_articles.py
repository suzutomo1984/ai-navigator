"""Build local article pages from the small, documented Markdown format."""
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
import argparse
import html
import json
import re

ROOT = Path(__file__).resolve().parent
BASE = 'https://ai-navigator.dev'
JST = timezone(timedelta(hours=9))


class PostError(ValueError):
    pass


def load_post(path):
    text = path.read_text(encoding='utf-8-sig')
    lines = text.splitlines()
    def fail(number, message):
        raise PostError(f'{path.name} の {number} 行目: {message}')
    if not lines or lines[0].strip() != '---':
        fail(1, '先頭に --- が必要です。')
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == '---')
    except StopIteration:
        fail(len(lines) or 1, '設定欄の終わりに --- が必要です。')
    meta = {'sources': []}; locations = {}; in_sources = False
    for number, line in enumerate(lines[1:end], 2):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if line.startswith('  - title: '):
            if not in_sources: fail(number, '出典は sources: の下に書いてください。')
            meta['sources'].append({'title': line.split(': ', 1)[1]})
        elif line.startswith('    url:'):
            if not in_sources or not meta['sources']: fail(number, '出典の title の後に url を書いてください。')
            meta['sources'][-1]['url'] = line.split(':', 1)[1].strip()
        elif line and not line.startswith(' '):
            if ':' not in line: fail(number, '項目名の後に : が必要です。')
            key, value = line.split(':', 1)
            if key in locations: fail(number, f'{key} が重複しています。')
            locations[key] = number
            in_sources = key == 'sources'
            if in_sources:
                if value.strip(): fail(number, 'sources: の後は改行してください。')
            else:
                if key not in {'slug','title','description','eyebrow','answer','published','checked','pr'}:
                    fail(number, f'知らない項目「{key}」です。')
                meta[key] = value.strip()
        else:
            fail(number, '設定欄の書き方を確認してください。')
    for key in ('slug', 'title', 'description', 'eyebrow', 'answer', 'checked'):
        if not meta.get(key): fail(locations.get(key, 1), f'{key} を入力してください。')
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', meta['slug']) or meta['slug'] == 'index':
        fail(locations['slug'], 'slug は英小文字・数字・ハイフンで指定してください（index は使えません）。')
    for key in ('published', 'checked'):
        if meta.get(key):
            try:
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', meta[key]): raise ValueError()
                date.fromisoformat(meta[key])
            except ValueError:
                fail(locations[key], f'{key} は YYYY-MM-DD で入力してください。')
    if meta.get('pr', 'false') not in ('true', 'false'):
        fail(locations['pr'], 'pr は true または false にしてください。')
    return meta, '\n'.join(lines[end+1:]).strip()


def is_draft(meta, today=None):
    today = today or datetime.now(JST).date()
    return not meta.get('published') or date.fromisoformat(meta['published']) > today


def inline(text):
    text = html.escape(text)
    text = re.sub(r'\[([^\]]+)\]\((https?://[^ )]+)\)', r'<a href="\2">\1</a>', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    return re.sub(r'`([^`]+)`', r'<code>\1</code>', text)


def markdown(body, headings=None):
    lines = body.splitlines(); out = []; i = 0; section = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1; continue
        m = re.fullmatch(r'【画像[:：]\s*(.*?)】', line)
        if m:
            out.append('<figure class="placeholder">画像: ' + html.escape(m[1]) + '</figure>'); i += 1; continue
        m = re.fullmatch(r'!\[([^\]]*)\]\((https?://[^\s)]+|/[^\s)]+)\)', line)
        if m:
            out.append('<figure class="article-image"><img src="'+html.escape(m[2], quote=True)+'" alt="'+html.escape(m[1], quote=True)+'"></figure>'); i += 1; continue
        m = re.match(r'^(#{2,3})\s+(.+)$', line)
        if m:
            n = len(m[1]); title = inline(m[2])
            if n == 2:
                section += 1
                ident = f'sec-{section}'
                if headings is not None:
                    headings.append((ident, re.sub(r'</?a\b[^>]*>', '', title)))
                out.append(f'<h2 id="{ident}">{title}</h2>')
            else:
                out.append(f'<h3>{title}</h3>')
            i += 1; continue
        if line.startswith('|') and i + 1 < len(lines) and re.match(r'^\|[\s:|\-]+\|$', lines[i+1].strip()):
            rows = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                rows.append([c.strip() for c in lines[i].strip().strip('|').split('|')]); i += 1
            out.append('<div class="table-wrap"><table><thead><tr>' + ''.join('<th>'+inline(c)+'</th>' for c in rows[0]) + '</tr></thead><tbody>' + ''.join('<tr>'+''.join('<td>'+inline(c)+'</td>' for c in row)+'</tr>' for row in rows[2:]) + '</tbody></table></div>'); continue
        m = re.match(r'^(?:- |\d+\. )', line)
        if m:
            ordered = line[0].isdigit(); tag = 'ol' if ordered else 'ul'; items = []
            pattern = r'^\d+\. ' if ordered else r'^- '
            while i < len(lines) and re.match(pattern, lines[i].strip()):
                items.append('<li>'+inline(re.sub(pattern, '', lines[i].strip()))+'</li>'); i += 1
            out.append(f'<{tag}>'+''.join(items)+f'</{tag}>'); continue
        para = [line]; i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r'^(#{2,3} |-|\d+\. |\||【画像[:：])', lines[i].strip()):
            para.append(lines[i].strip()); i += 1
        out.append('<p>'+inline(' '.join(para))+'</p>')
    return '\n'.join(out)


def faq(body):
    match = re.search(r'^## よくある質問\s*\n(.*?)(?=^## |\Z)', body, re.M | re.S)
    if not match:
        return []
    result = []
    for q, answer in re.findall(r'^### ([^\n]+)\n(.*?)(?=^### |\Z)', match[1], re.M | re.S):
        answer = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', answer.strip())
        result.append({'@type': 'Question', 'name': q.strip(), 'acceptedAnswer': {'@type': 'Answer', 'text': re.sub(r'\*\*|`', '', answer)}})
    return result


CSS = '''
#article-main { max-width:760px; margin:var(--header-h) auto 0; padding:30px 22px 100px; line-height:1.8; overflow-wrap:anywhere; }
#article-main h1 { font-family:"Noto Serif JP",serif; font-size:clamp(27px,5vw,40px); line-height:1.4; margin:12px 0; }
#article-main h2 { font-size:23px; border-bottom:1px solid var(--rule-strong); margin:42px 0 14px; padding-bottom:8px; scroll-margin-top:calc(var(--header-h) + 16px); }
#article-main h3 { font-size:18px; font-weight:700; margin:28px 0 8px; }
#article-main p, #article-main ul, #article-main ol { margin:14px 0; line-height:1.8; }
#article-main ul, #article-main ol { padding-left:1.5em; }
.crumb,.article-meta { color:var(--ink-muted); font-size:12px; }
.eyebrow { color:var(--brand-red); font-weight:700; font-size:12px; margin-top:20px; }
.answer { border-left:3px solid var(--brand-red); background:rgba(255,51,95,.06); padding:16px; margin:24px 0; }
.answer-label { display:block; color:var(--brand-red); font-size:12px; font-weight:700; }
.draft-banner { padding:14px 16px; margin-bottom:24px; border:2px solid var(--brand-red); border-radius:var(--radius-sm); background:var(--paper); color:var(--brand-red); font-weight:700; overflow-wrap:anywhere; }
.draft-badge { display:inline-block; color:var(--brand-red); border:1px solid var(--brand-red); border-radius:var(--radius-sm); padding:1px 7px; font-size:12px; font-weight:700; }
.article-image { margin:22px 0; } .article-image img { display:block; max-width:100%; height:auto; }
.article-body ul > li, .sources ul > li { list-style:disc; }
.article-body ol > li { list-style:decimal; }
.article-toc { border:1px solid var(--rule); border-radius:var(--radius-sm); background:var(--paper); padding:14px 18px; }
.article-toc summary { cursor:pointer; font-weight:700; }
.article-toc summary::before { content:'＋'; margin-right:8px; }
.article-toc[open] summary::before { content:'−'; }
#article-main .article-toc ol { margin:12px 0 0; padding-left:1.6em; }
.article-toc li { list-style:decimal; margin:6px 0; line-height:1.7; }
.article-toc a { color:var(--ink); }
.placeholder { border:1px dashed var(--rule-strong); aspect-ratio:16/9; display:grid; place-items:center; margin:22px 0; padding:16px; text-align:center; color:var(--ink-muted); }
.sources { border-top:1px solid var(--rule); margin-top:40px; padding-top:16px; font-size:13px; }
.table-wrap { overflow-x:auto; max-width:100%; } table { border-collapse:collapse; font-size:14px; } th,td { border:1px solid var(--rule); padding:8px; }
.article-card { display:block; padding:22px 0; border-bottom:1px solid var(--rule); color:inherit; } .article-card h2 { margin:0 0 8px!important; border:0!important; } .article-card p { margin:4px 0!important; }
'''


def shell(title, description, url, content, structured=None, is_article=False, draft=False):
    about = (ROOT/'about.html').read_text(encoding='utf-8')
    scripts = about[about.index('  <!-- 旧ドメイン'):about.index('  <title>')]
    fonts = about[about.index('  <link rel="preconnect"'):about.index('  <link rel="stylesheet"')]
    noscript = about[about.index('  <!-- Google Tag Manager (noscript)'):about.index('  <!-- ヘッダー:')]
    header = about[about.index('  <header id="header">'):about.index('  <main id="about-main">')]
    header = header.replace('class="tab-btn active"', 'class="tab-btn"').replace('class="bnav-item active"', 'class="bnav-item"')
    header = header.replace('class="tab-btn" href="/articles/"', 'class="tab-btn active" href="/articles/"').replace('class="bnav-item" href="/articles/"', 'class="bnav-item active" href="/articles/"')
    e = lambda s: html.escape(str(s), quote=True)
    ld = '' if structured is None else '<script type="application/ld+json">'+json.dumps(structured, ensure_ascii=False).replace('<', '\\u003c')+'</script>'
    return f'''<!DOCTYPE html><html lang="ja"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">{scripts}
<title>{e(title)} | AI Navigator</title><meta name="description" content="{e(description)}">{'<meta name="robots" content="noindex">' if draft else ''}<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(description)}"><meta property="og:type" content="{'article' if is_article else 'website'}"><meta property="og:url" content="{e(url)}"><meta property="og:image" content="https://ai-navigator.dev/ogp.png"><meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{e(title)}"><meta name="twitter:description" content="{e(description)}">{fonts}<link rel="stylesheet" href="/style.css"><link rel="canonical" href="{e(url)}">{ld}<style>{CSS}</style></head><body>{noscript}{header}<main id="article-main">{content}</main></body></html>'''


def render_article(meta, body, draft=False):
    e = html.escape; url = BASE+'/articles/'+meta['slug']; org = {'@type':'Organization','name':'AI Navigator'}
    article = {'@context':'https://schema.org','@type':'Article','headline':meta['title'],'description':meta['description'],'dateModified':meta['checked'],'author':org,'publisher':org,'mainEntityOfPage':url}
    if meta.get('published'): article['datePublished'] = meta['published']
    breadcrumb = {'@context':'https://schema.org','@type':'BreadcrumbList','itemListElement':[{'@type':'ListItem','position':i,'name':name,'item':link} for i,(name,link) in enumerate([('TOP',BASE+'/'),('記事',BASE+'/articles/'),(meta['title'],url)],1)]}
    structured = [article, {'@context':'https://schema.org','@type':'FAQPage','mainEntity':faq(body)}, breadcrumb]
    sources = ''.join('<li><a target="_blank" rel="noopener noreferrer" href="'+e(s.get('url',''),quote=True)+'">'+e(s['title'])+'</a></li>' if s.get('url') else '<li>'+e(s['title'])+'</li>' for s in meta['sources'])
    published = '公開 '+e(meta['published']) if meta.get('published') else '公開前'
    headings = []
    body_html = markdown(body, headings)
    items = ''.join(f'<li><a href="#{ident}">{title}</a></li>' for ident, title in headings)
    toc = ('<details class="article-toc" open><summary>目次</summary><ol>'+items+'</ol></details>'
           '<script>(function(){const toc=document.currentScript.previousElementSibling;'
           'const mobile=window.matchMedia("(max-width: 768px)");'
           'function update(){toc.open=!mobile.matches;} update();'
           'if(mobile.addEventListener) mobile.addEventListener("change",update);'
           'else if(mobile.addListener) mobile.addListener(update);})();</script>') if headings else ''
    content = f'''<nav class="crumb"><a href="/">TOP</a> › <a href="/articles/">記事</a> › {e(meta['title'])}</nav><div class="eyebrow">{'【PR】 ' if meta.get('pr') == 'true' else ''}{e(meta['eyebrow'])}</div><h1>{e(meta['title'])}</h1><div class="article-meta">確認日 {e(meta['checked'])} ・ {published} ・ AI Navigator</div><aside class="answer"><span class="answer-label">先に結論</span>{e(meta['answer'])}</aside>{toc}<article class="article-body">{body_html}</article><section class="sources"><h2>出典</h2><ul>{sources}</ul></section>'''
    if draft:
        content = '<div class="draft-banner">下書き（公開前）・このページは本番に出ません</div>' + content
    return shell(meta['title'],meta['description'],url,content,structured,True,draft)


def build(root=ROOT, publish=False, today=None):
    root = Path(root)
    today = today or datetime.now(JST).date()
    posts = []
    slugs = set()
    for path in sorted((root/'posts').glob('*.md')):
        if path.name.startswith('_'):
            continue
        meta, body = load_post(path)
        if meta['slug'] in slugs:
            number = next((i for i, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1) if line.startswith('slug:')), 1)
            raise PostError(f'{path.name} の {number} 行目: slug「{meta["slug"]}」が他の記事と重複しています。')
        slugs.add(meta['slug'])
        if not publish or not is_draft(meta, today):
            posts.append((meta, body))
    posts.sort(key=lambda item:item[0]['checked'], reverse=True)
    # Parse and render every article before touching any existing HTML.
    pages = {m['slug']+'.html': render_article(m, body, is_draft(m, today)) for m,body in posts}
    cards = ''.join('<a class="article-card" href="/articles/'+html.escape(m['slug'])+'">'+('<span class="draft-badge">下書き</span>' if is_draft(m,today) else '')+'<h2>'+html.escape(m['title'])+'</h2><p>'+html.escape(m['description'])+'</p><span class="article-meta">確認日 '+html.escape(m['checked'])+'</span></a>' for m,_ in posts)
    pages['index.html'] = shell('記事','AI Navigatorの記事一覧',BASE+'/articles/','<nav class="crumb"><a href="/">TOP</a> › 記事</nav><h1>記事</h1>'+cards)
    if publish:
        site_text, llms_text = publish_indexes(root, posts)
    output = root/'articles'; output.mkdir(exist_ok=True)
    for filename, content in pages.items():
        (output/filename).write_text(content,encoding='utf-8')
    if publish:
        for old in output.glob('*.html'):
            if old.name not in pages:
                old.unlink()
        (root/'sitemap.xml').write_text(site_text,encoding='utf-8')
        (root/'llms.txt').write_text(llms_text,encoding='utf-8')
    return posts


def publish_indexes(root, posts):
    site = root/'sitemap.xml'; xml = site.read_text(encoding='utf-8')
    xml = re.sub(r'\s*<url>\s*<loc>https://ai-navigator\.dev/articles/[^<]*</loc>\s*<lastmod>[^<]*</lastmod>\s*</url>', '', xml)
    if posts:
        entries = [(BASE+'/articles/',posts[0][0]['checked'])]+[(BASE+'/articles/'+m['slug'],m['checked']) for m,_ in posts]
        xml = xml.replace('</urlset>', ''.join('\n  <url>\n    <loc>'+html.escape(u)+'</loc>\n    <lastmod>'+d+'</lastmod>\n  </url>' for u,d in entries)+'\n</urlset>')
    llms = root/'llms.txt'; text = llms.read_text(encoding='utf-8')
    text = re.sub(r'^- \[.*?\]\(https://ai-navigator\.dev/articles/[^)]*\):.*\n?', '', text, flags=re.M)
    lines = ''.join('- ['+m['title']+']('+BASE+'/articles/'+m['slug']+'): '+m['description']+'\n' for m,_ in posts)
    if '## 更新頻度' not in text:
        raise ValueError('llms.txt に「## 更新頻度」がありません。')
    text = text.replace('## 更新頻度', lines+'## 更新頻度', 1)
    return xml, text


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='記事を生成します。')
    parser.add_argument('--publish', action='store_true', help='公開済みの記事だけを生成')
    args = parser.parse_args()
    try:
        build(publish=args.publish)
    except (PostError, ValueError, OSError) as exc:
        parser.exit(1, f'記事を作れません: {exc}\n')

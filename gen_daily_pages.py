"""日次ページ（朝刊・夕刊）生成プロトタイプ。

本番 articles.json を読み、addedAt の時刻帯で朝刊/夕刊に振り分けて
静的HTMLを生成する。parse_news.py に組み込む関数の原型。

朝刊 = 午前バッチ(addedAt時刻 < 12時)の当日新着記事
夕刊 = 午後バッチ(addedAt時刻 >= 12時)の当日新着記事
編集まとめ(dailySummary)は朝夕で同じものを流用（記事は新着差し替えで重複しない）。
"""
from __future__ import annotations

import html
import json
from collections import OrderedDict
from pathlib import Path

# カテゴリ表示順とラベル・絵文字（parse_news.py の CATEGORY_MAP に合わせる想定の暫定版）
CAT_DISPLAY: "OrderedDict[str, tuple[str, str]]" = OrderedDict([
    ("strategy", ("🎯", "戦略・経営")),
    ("sales-marketing", ("📣", "営業・マーケティング")),
    ("productivity", ("⚡", "業務効率化")),
    ("back-office", ("🧾", "バックオフィス")),
    ("info-mgmt", ("🗂️", "情報管理")),
    ("side-business", ("💰", "副業・個人開発")),
    ("ai-tech", ("🤖", "AI技術")),
    ("official", ("🚀", "公式リリース")),
    ("other", ("📰", "その他")),
])

EDITION_LABEL = {"am": "朝刊", "pm": "夕刊"}
EDITION_EYEBROW = {"am": "Morning Edition", "pm": "Evening Edition"}


def esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def render_item(a: dict) -> str:
    pick = '<span class="pick-badge">PICK</span>' if a.get("isPick") else ""
    src = esc(a.get("source", ""))
    return f"""      <a class="item" href="{esc(a.get('url',''))}" target="_blank" rel="nofollow noopener">
        <div class="item-top">{pick}<span class="src">{src}</span></div>
        <h3 class="item-title">{esc(a.get('title',''))}</h3>
        <p class="item-summary">{esc(a.get('summary',''))}</p>
        <span class="item-cta">出典元で読む →</span>
      </a>"""


def render_category(cat_id: str, articles: list[dict]) -> str:
    emoji, label = CAT_DISPLAY.get(cat_id, ("📰", cat_id))
    items = "\n".join(render_item(a) for a in articles)
    return f"""  <section class="cat">
    <div class="cat-head"><span class="cat-emoji">{emoji}</span><span class="cat-name">{esc(label)}</span><span class="cat-count">{len(articles)}件</span></div>
    <div class="feed">
{items}
    </div>
  </section>"""


def build_page(date_str: str, edition: str, articles: list[dict],
               daily_summary: str, day_of_week_jp: str) -> str:
    """朝刊/夕刊1ページ分のHTMLを返す。"""
    # カテゴリ別にグルーピング（表示順は CAT_DISPLAY 準拠、各カテゴリ内は isPick→rankingScore順）
    by_cat: "OrderedDict[str, list[dict]]" = OrderedDict()
    for cat_id in CAT_DISPLAY:
        bucket = [a for a in articles if a.get("category") == cat_id]
        if bucket:
            bucket.sort(key=lambda x: (not x.get("isPick"), -(x.get("rankingScore") or 0)))
            by_cat[cat_id] = bucket
    # CAT_DISPLAY外のカテゴリも拾う
    known = set(CAT_DISPLAY)
    for a in articles:
        c = a.get("category", "other")
        if c not in known:
            by_cat.setdefault("other", []).append(a)

    cats_html = "\n\n".join(render_category(cid, arts) for cid, arts in by_cat.items())
    ed_label = EDITION_LABEL[edition]
    ed_eyebrow = EDITION_EYEBROW[edition]
    title = f"{date_str} {ed_label}｜AI Navigator"
    y, m, dd = date_str.split("-")
    date_disp = f"{int(y)}年{int(m)}月{int(dd)}日"

    other_ed = "pm" if edition == "am" else "am"
    other_label = EDITION_LABEL[other_ed]

    return f"""<title>{esc(title)}</title>
<link rel="stylesheet" href="../style.css">
<style>
  body {{ background: var(--bg-primary); color: var(--text-primary); }}
  .daily-wrap {{ max-width: 760px; margin: 0 auto; padding: 0 20px 80px; }}
  .daily-topbar {{ border-bottom: 1px solid var(--border); background: var(--bg-surface); position: sticky; top: 0; z-index: 10; }}
  .daily-topbar-inner {{ max-width: 760px; margin: 0 auto; padding: 0 20px; height: 58px; display: flex; align-items: center; justify-content: space-between; }}
  .daily-brand {{ display: flex; align-items: center; gap: 9px; font-weight: 700; text-decoration: none; color: var(--text-primary); }}
  .daily-brand .dot {{ width: 9px; height: 9px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 12px var(--accent); }}
  .daily-back {{ font-size: 0.82rem; color: var(--text-secondary); text-decoration: none; padding: 6px 12px; border: 1px solid var(--border); border-radius: 999px; }}
  .daily-back:hover {{ border-color: var(--border-hover); color: var(--text-primary); }}
  .daily-head {{ padding: 48px 0 30px; }}
  .daily-eyebrow {{ font-size: 0.72rem; font-weight: 600; letter-spacing: 0.14em; text-transform: uppercase; color: var(--accent); margin: 0 0 12px; }}
  .daily-title {{ margin: 0 0 16px; font-size: 2.0rem; line-height: 1.32; font-weight: 800; letter-spacing: -0.02em; }}
  .daily-meta {{ display: flex; flex-wrap: wrap; gap: 8px 16px; font-size: 0.82rem; color: var(--text-muted); }}
  .daily-meta b {{ color: var(--text-secondary); font-weight: 600; }}
  .lead-block {{ margin: 36px 0 12px; }}
  .lead-block .lead {{ margin: 0; font-size: 1.1rem; line-height: 1.95; color: var(--text-primary); }}
  .editor-note {{ display: flex; align-items: center; gap: 9px; margin: 24px 0; font-size: 0.78rem; color: var(--text-muted); }}
  .editor-note .line {{ flex: 1; height: 1px; background: var(--border); }}
  .cat {{ margin-top: 44px; }}
  .cat-head {{ display: flex; align-items: baseline; gap: 10px; margin: 0 0 16px; padding-bottom: 12px; border-bottom: 1px solid var(--border); }}
  .cat-emoji {{ font-size: 1.15rem; }}
  .cat-name {{ font-size: 1.04rem; font-weight: 800; }}
  .cat-count {{ font-size: 0.76rem; color: var(--text-muted); }}
  .feed {{ display: flex; flex-direction: column; gap: 12px; }}
  .item {{ display: block; text-decoration: none; background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: 17px 19px; transition: border-color .16s, background .16s; }}
  .item:hover {{ background: var(--bg-card-hover); border-color: var(--border-hover); }}
  .item-top {{ display: flex; align-items: center; gap: 9px; margin-bottom: 8px; flex-wrap: wrap; }}
  .pick-badge {{ font-size: 0.62rem; font-weight: 700; color: var(--accent); background: var(--accent-subtle); padding: 2px 8px; border-radius: 999px; border: 1px solid var(--border-accent); }}
  .src {{ font-size: 0.74rem; color: var(--text-muted); }}
  .item-title {{ margin: 0 0 6px; font-size: 1.0rem; font-weight: 700; line-height: 1.5; }}
  .item-summary {{ margin: 0; font-size: 0.88rem; color: var(--text-secondary); line-height: 1.72; }}
  .item-cta {{ margin-top: 10px; font-size: 0.77rem; color: var(--accent); font-weight: 600; display: inline-block; }}
  .daily-footer {{ margin-top: 60px; padding-top: 28px; border-top: 1px solid var(--border); font-size: 0.8rem; color: var(--text-muted); line-height: 1.8; }}
  .daily-footer h2 {{ font-size: 0.74rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: var(--text-secondary); margin: 0 0 12px; }}
  .daily-footer a {{ color: var(--text-secondary); }}
  .disclaimer {{ margin-top: 16px; padding: 14px 16px; background: var(--bg-surface); border: 1px solid var(--border); border-radius: var(--radius-sm); font-size: 0.76rem; }}
  @media (max-width: 560px) {{ .daily-title {{ font-size: 1.5rem; }} }}
</style>

<div class="daily-topbar">
  <div class="daily-topbar-inner">
    <a class="daily-brand" href="../index.html"><span class="dot"></span>AI Navigator</a>
    <a class="daily-back" href="../index.html">← ニュース一覧へ</a>
  </div>
</div>

<div class="daily-wrap">
  <header class="daily-head">
    <p class="daily-eyebrow">{ed_eyebrow}</p>
    <h1 class="daily-title">{date_disp}の{ed_label}</h1>
    <div class="daily-meta">
      <span><b>{esc(day_of_week_jp)}</b></span>
      <span>掲載 <b>{len(articles)}件</b></span>
      <span>編集：AI Navigator 編集部</span>
    </div>
  </header>

  <div class="lead-block">
    <p class="lead">{esc(daily_summary)}</p>
  </div>

  <div class="editor-note">
    <span class="line"></span><span>この{ed_label}は編集部がその配信回の新着から抜粋・要約しました</span><span class="line"></span>
  </div>

{cats_html}

  <footer class="daily-footer">
    <h2>このサイトについて</h2>
    <p>AI Navigator は、AIビジネス活用に関する記事を毎日自動で収集し、中小企業・非エンジニアの実務目線で要約・整理して配信する個人運営のニュースメディアです。各記事の要約は当サイトが独自に作成しており、著作権は元記事の各著者・媒体に帰属します。</p>
    <p>運営: AI Navigator 編集部　／　お問い合わせ・掲載削除のご依頼: <a href="mailto:example@example.com">example@example.com</a>（※プロト）</p>
    <div class="disclaimer">掲載記事の著作権は各権利者に帰属します。要約は紹介を目的としたものです。掲載取り下げをご希望の権利者の方は上記窓口までご連絡ください。</div>
  </footer>
</div>"""


DOW_JP = {"Mon": "月曜日", "Tue": "火曜日", "Wed": "水曜日", "Thu": "木曜日",
          "Fri": "金曜日", "Sat": "土曜日", "Sun": "日曜日"}


def main() -> None:
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else "articles.json"
    outdir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("daily")
    outdir.mkdir(exist_ok=True)

    data = json.loads(Path(src).read_text(encoding="utf-8"))
    arts = data["articles"]
    dates = {d["date"]: d for d in data.get("dates", [])}

    # 直近の朝バッチ・夕バッチを addedAt から特定
    # （プロト: 6/25朝=07時台, 6/24夕=19時台 を固定指定）
    targets = [
        ("2026-06-25", "am", "2026-06-25T07"),
        ("2026-06-24", "pm", "2026-06-24T19"),
    ]
    for date_str, edition, prefix in targets:
        batch = [a for a in arts if a.get("addedAt", "").startswith(prefix)]
        if not batch:
            print(f"[SKIP] {date_str} {edition}: 新着0件")
            continue
        dmeta = dates.get(date_str, {})
        summary = dmeta.get("dailySummary", "").strip() or "（本日の編集まとめは準備中です）"
        dow = DOW_JP.get(dmeta.get("dayOfWeek", "")[:3], dmeta.get("dayOfWeek", ""))
        html_out = build_page(date_str, edition, batch, summary, dow)
        outpath = outdir / f"{date_str}-{edition}.html"
        outpath.write_text(html_out, encoding="utf-8")
        print(f"[OK] {outpath} : {len(batch)}件")


if __name__ == "__main__":
    main()

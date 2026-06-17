# AGENTS.md — AIエージェント向け作業ガイド

> このリポジトリ（ai-navigator）を改修するAI（Claude / Codex 等）は、**作業前に必ずこのファイルを読むこと**。
> 過去に実際に起きた事故と、その再発防止ルールを記載している。読まずに触ると同じ轍を踏む。

## このプロジェクトの全体像

AI・自動化ニュースを毎日自動収集して表示するニュースサイト。**2リポジトリ構成**：

- **ai-navigator（このリポ）** = フロントエンド + 変換ロジック
  - `parse_news.py`: `自動ニュース配信/*_テックニュース.md` → `articles.json` に変換
  - `app.js` / `*.html` / `style.css`: 表示
- **suzutomo-organization/my-vault** = 収集 + Actions オーケストレーション
  - `.github/scripts/auto_news.py`: RSS収集 → Gemini要約 → MD生成
  - `.github/workflows/auto-news.yml`（収集）→ `personal-pick.yml`（変換+デプロイ）

このリポは my-vault の**サブモジュール**。本番配信は `gh-pages` ブランチ → Cloudflare Pages（https://ai-news-eev.pages.dev）。

---

## 🚨 絶対に守るルール（過去の事故ベース）

### 1. OGPサムネ取得は「並列」を維持する。直列に戻すな
- **事故（2026-06-17）**: サムネ取得を直列HTTP（1件最大8秒）にしていたため、記事が増えると `articles.json` の書き出し前にActionsがタイムアウトし、**本番が約2ヶ月前の日付で更新停止**した（Actionsはsuccess表示のまま＝気づきにくい）。
- **現在の実装**: `parse_news.py` のサムネ付与は `ThreadPoolExecutor`（`OGP_WORKERS`, 既定20）で**並列化**済み。新規2400件超でも約70秒で完走する。
- **禁止**: 並列を直列に戻すこと。`OGP_BUDGET_SEC` を極端に小さくしてサムネを大量スキップさせること。
- **要件**: サムネは原則全件出す。一度取得すれば `articles.json` の `thumbnail` がキャッシュとして次回引き継がれる。サムネ無しが残るのはOGP画像を持たないサイト（数%）のみで許容。
- **環境変数**: `OGP_WORKERS`（並列数, 既定20）, `OGP_BUDGET_SEC`（全体時間上限秒, 既定600。0で新規取得停止＝キャッシュのみ）。

### 2. カテゴリを追加/変更するときは「3点同期」する
カテゴリ分類の真実源は **「Geminiが出力するMarkdownのH2見出し」だけ**。`auto_news.py` のSOURCESの `category` フィールドは**分類に使われないデッドメタデータ**（Geminiにはソース名+記事タイトル+URLしか渡らない）。

新カテゴリを足すときに同期すべき3箇所（1つでも抜けると空振りする）：
1. **my-vault `auto_news.py`**: SOURCESに収集元RSS追加 ＋ `summarize_with_gemini` のプロンプト出力フォーマットに `## 絵文字 カテゴリ名` セクションを追加
2. **このリポ `parse_news.py`**: `CATEGORY_MAP` に `(id, label, 絵文字, [keywords])` を1行追加（`normalize_category` がH2見出しをkeywordで先勝ち走査して分類する）
3. **このリポ `app.js`**: `CAT_COLORS` に `"id": "#色"` を追加（**無いとサイドバーでその色だけグレーになり浮く**）

フロントのサイドバーは `articles.json` の `categories` を動的描画する（`articleCount>0` かつ `id!="official"` で自動表示）。HTML自体の改修は不要。

### 3. gh-pages の上書き事故に注意
- `personal-pick.yml` は「gh-pages の既存 `articles.json`」を取得してサムネキャッシュを引き継いだ上で再生成 → `gh-pages` に force push する。
- **このリポへのPRを `main` にマージすると、gh-pages がmainの内容で上書きされ得る**（articles.jsonが古くなる）。
- **マージ後の正しい手順**: my-vault側でサブモジュール参照を更新&push → `auto-news.yml` を手動実行（`gh workflow run auto-news.yml`）して再生成し、本番を最新に戻す。

---

## デバッグの定石

### 「Actionsはsuccessなのに本番が古い日付で止まっている」
→ **OGP取得を疑え**。切り分け方：
```bash
# OGP無効で即完走するか確認（最新日付・全記事が出れば犯人はOGP）
OGP_BUDGET_SEC=0 python parse_news.py
```

### ローカルでの確認
```bash
# 並列OGP込みで本番同等に生成（約70秒）
python parse_news.py
# articles.json の記事数・最新日付・サムネ率を確認してから本番反映すること
```

---

## 変更後に必ず確認すること
- [ ] `python -c "import py_compile; py_compile.compile('parse_news.py', doraise=True)"` が通る
- [ ] ローカル生成で記事数・最新日付が想定通り（前回から激減していないか）
- [ ] サムネ率が大きく落ちていないか（OGP関連を触った場合）
- [ ] カテゴリを足したなら上記「3点同期」が揃っているか

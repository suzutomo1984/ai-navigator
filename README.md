# AI Navigator

AI・自動化・開発ツール領域のニュースを自動収集し、ブラウザで閲覧できるパーソナルニュースリーダー。

**本番URL**: https://ai-news-eev.pages.dev

---

## 概要

GitHub Actionsで毎日自動更新される3ページ構成のニュースサイト。

| ページ | 内容 |
|---|---|
| 📰 AIニュース | Zenn・Qiita・HackerNews等から収集したAI関連記事 |
| 📢 公式リリース | OpenAI・Anthropic・Google等の公式ブログ・SDKリリース |
| 🌟 GitHub Trending | 毎日のGitHub Trendingリポジトリ（stars/language/日本語説明付き） |

---

## 構成ファイル

```
ai-navigator/
├── index.html        # AIニュースページ
├── official.html     # 公式リリースページ
├── trending.html     # GitHub Trendingページ
├── style.css         # 全ページ共通スタイル（ダークテーマ）
├── app.js            # AIニュースのフロントエンドロジック
├── official.js       # 公式ページのフロントエンドロジック
├── trending.js       # Trendingページのフロントエンドロジック
├── parse_news.py     # MD → articles.json 変換・Trending取得・Gemini翻訳
└── articles.json     # 全データ（記事・trending・カテゴリ）
```

---

## 自動化フロー

```
毎朝7時（JST）
  ↓ auto-news.yml: RSSから記事収集 → Geminiで要約 → MD生成
  ↓ personal-pick.yml: パーソナルピック生成
  ↓ parse_news.py: MD → articles.json 変換
       + GitHub Trending RSS取得 → GitHub API補完 → Gemini日本語翻訳
  ↓ gh-pagesブランチへデプロイ
  ↓ Cloudflare Pagesが自動公開
```

このリポジトリは `suzutomo-organization/my-vault` のサブモジュールとして管理されており、
GitHub Actionsは my-vault 側で実行される。

---

## ローカル確認

```bash
# articles.json を再生成
python parse_news.py

# ローカルサーバー起動（file://では動かないためHTTPサーバーが必須）
python -m http.server 8765
# → http://localhost:8765
```

---

## デプロイ

```bash
# ai-navigator に変更を加えたら
git add .
git commit -m "feat: ..."
git push origin main

# my-vault 側のサブモジュール参照も更新する（重要）
cd ..
git add ai-navigator
git commit -m "chore: ai-navigator更新"
git push origin master
# → personal-pick.yml が自動でgh-pagesにデプロイ
```

---

## ⚠️ よくある落とし穴（改修前に必読）

> AIエージェントで改修する場合は **[AGENTS.md](AGENTS.md)** に詳細あり。

1. **OGPサムネ取得は並列を維持する**
   `parse_news.py` のサムネ取得は `ThreadPoolExecutor`（既定20並列）。
   直列に戻すと記事増加時に `articles.json` 書き出し前にActionsがタイムアウトし、
   **本番が古い日付で更新停止**する（Actionsはsuccess表示のまま）。実際に2026-06-17に発生。
   調整は環境変数 `OGP_WORKERS` / `OGP_BUDGET_SEC`（既定600秒、0で取得停止）。

2. **カテゴリ追加は3点同期**
   ① my-vault `auto_news.py`（SOURCES＋Geminiプロンプトの出力セクション）
   ② このリポ `parse_news.py` の `CATEGORY_MAP`
   ③ このリポ `app.js` の `CAT_COLORS`（無いとサイドバーで色が浮く）
   ※ `auto_news.py` のSOURCESの `category` は分類に使われない（実分類はGemini出力のH2見出し）。

3. **`push: main` で gh-pages を更新するworkflowを追加しない**
   かつて `deploy.yml`（`on: push: main` → mainをgh-pagesにforce push）があり、PRマージのたびに
   mainの古い `articles.json` で本番を上書きして繰り返し巻き戻した（2026-06-17に根治）。
   現在は deploy.yml を削除し `articles.json` は gitignore 済み。本番配信は my-vault の
   `personal-pick.yml` が担う。同種のworkflowを再追加しないこと。

「本番が古い日付で止まっている」ときは、まず `OGP_BUDGET_SEC=0 python parse_news.py` で
OGP無効にして即完走するか確認する（最新日付が出れば犯人はOGP取得）。

---

## 開発履歴

| Phase | 内容 |
|---|---|
| Phase 0-1（2026-03-18） | MVP構築・Cloudflare Pages公開 |
| Phase 2（2026-03-19） | UI v2 - 左サイドバー + 3カラムグリッド |
| Phase 3（2026-03-22〜） | 公式リリースページ・サムネイル表示 |
| Phase 4（2026-03-27） | GitHub Trendingページ・公式カテゴリ・完全自動化 |

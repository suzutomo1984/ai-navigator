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

## 開発履歴

| Phase | 内容 |
|---|---|
| Phase 0-1（2026-03-18） | MVP構築・Cloudflare Pages公開 |
| Phase 2（2026-03-19） | UI v2 - 左サイドバー + 3カラムグリッド |
| Phase 3（2026-03-22〜） | 公式リリースページ・サムネイル表示 |
| Phase 4（2026-03-27） | GitHub Trendingページ・公式カテゴリ・完全自動化 |

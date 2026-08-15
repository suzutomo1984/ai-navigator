---
title: AI Navigator 全自動デプロイフロー 解説
created: 2026-03-19
last_updated: 2026-03-27
tags: [ai-navigator, github-actions, 解説]
---

# AI Navigator 全自動デプロイフロー 解説

---

## 概要

AI Navigatorは、毎朝自動でAIニュースを収集・要約し、Webサイトとして公開するシステム。
人が何もしなくても、スケジュールに従って収集→要約→公開まで全自動で完結する。

**本番URL**: https://ai-navigator.dev
**3つのページ**: 📰 AIニュース / 📢 公式リリース / 🌟 GitHub Trending

---

## 登場するリポジトリ

| リポジトリ | 用途 |
|---|---|
| `suzutomo-organization/my-vault` | GitHub Actionsの実行場所。ニュース記事（Markdown）の保存先 |
| `suzutomo1984/ai-navigator` | Webサイトのソースコード。my-vaultのサブモジュールとして管理 |

---

## フロー詳細

### 1. Schedule Trigger（自動起動）

- 毎朝 22:00 UTC（= JST 07:00）にGitHub Actionsを自動起動
- `suzutomo-organization/my-vault` リポジトリのワークフローが動き出す
- 手動実行も可能（テスト用）

---

### 2. ① 自動ニュース配信（auto-news.yml）

**実行スクリプト: `.github/scripts/auto_news.py`**

**AIニュース収集・要約**
- Zenn・Qiita・Note・Dev.to・Hacker News・HuggingFace Blog・Reddit等のRSSフィードを巡回
- 公式ブログ（OpenAI Blog・Google AI Blog・Google DeepMind・Gemini Blog・Microsoft Foundry Blog）も収集
- 公式SDKリリース（Claude Code・Anthropic SDK・OpenAI SDK・MCP・LangChain・LlamaIndex等）は `skip_date_filter: True` で24hフィルター免除（更新頻度が低いため）
- 一般記事は24時間以内のみ対象・URL重複を自動除外
- Gemini API（`gemini-3-flash-preview`）で日本語要約を生成
- 公式記事は「📢 公式リリース / AI企業アップデート」セクションに分類するようプロンプト指示

**Markdownファイル生成**
- 要約結果を `自動ニュース配信/YYYY-MM-DD_テックニュース.md` として保存
- ファイルが200バイト未満（生成失敗）の場合、parse_news.pyがスキップ

**my-vault masterへ保存**
- 生成されたMarkdownをmasterブランチにコミット
- GitHub Actions bot（`github-actions[bot]`）が自動実行

---

### 3. ② パーソナルピック（personal-pick.yml）

① の完了を検知して自動的に起動（`workflow_run` トリガー）。

**実行スクリプト: `.github/scripts/personal_pick.py`**

- デイリーノート（直近3日分）から友也の活動文脈を抽出
- Gemini APIで記事を分析し「必読ピック」3〜5記事を生成
- `自動ニュース配信/YYYY-MM-DD_パーソナルピック.md` として保存
- Gemini APIが503エラーの場合は最大3回・5秒間隔で自動リトライ

**サイト表示データ整形**

**実行スクリプト: `ai-navigator/parse_news.py`**

- `自動ニュース配信/` フォルダのMarkdownを全件解析 → `articles.json` 生成
- `isOfficial: true` の記事は `category: "official"` に強制変換
- GitHub Trending RSS（daily + weekly）を直接取得（最大25件/日）
- GitHub APIでstars・forks・language・descriptionを自動補完
- Gemini APIで英語descriptionを日本語翻訳
- 毎日積み上げ蓄積（過去分保持）・重複除去・🔥連続日数トラッキング
- gh-pagesからの既存 `articles.json` を引き継いでサムネキャッシュを保持

> **なぜJSONに変換するか？**
> WebサイトはMarkdownを直接読めない。JavaScriptがデータを取得・表示するためにJSON形式への変換が必要。

**AI Navigator gh-pagesへデプロイ**
- `index.html` / `app.js` / `style.css` / `official.html` / `official.js` / `trending.html` / `trending.js` / `articles.json` を一時ディレクトリにまとめる
- `suzutomo1984/ai-navigator` の `gh-pages` ブランチへforce pushでデプロイ
- デプロイ失敗してもワークフロー全体は止まらない（`continue-on-error: true`）

---

### 4. Cloudflare Pages（自動公開）

- `suzutomo1984/ai-navigator` の `gh-pages` ブランチを常時監視
- ブランチの変更を検知すると自動でビルド＆公開
- 公開URL: `ai-navigator.dev`

---

## articles.json のデータ構造

`parse_news.py` が生成するJSONファイル。Webサイト全体のデータソース。

```json
{
  "totalArticles": 801,
  "officialCount": 15,
  "trendingCount": 20,
  "articles": [{
    "id": "2026-03-27_1",
    "date": "2026-03-27",
    "title": "記事タイトル",
    "url": "https://...",
    "source": "Claude Code Releases",
    "category": "official",
    "summary": "要約テキスト",
    "thumbnail": "https://opengraph.githubassets.com/1/...",
    "isOfficial": true,
    "isPick": false,
    "rankingTier": 1
  }],
  "trending": [{
    "title": "owner/repo",
    "url": "https://github.com/owner/repo",
    "summary": "日本語要約",
    "stars": 12345,
    "language": "Python",
    "trendingDays": 3
  }]
}
```

### カテゴリ一覧

| id | 表示名 | 内容 |
|---|---|---|
| `official` | 📢 公式リリース | isOfficialの記事が自動分類。公式ページ専用 |
| `ai-agent` | 🤖 AI/MCP | AIエージェント・LLM・Claude関連 |
| `obsidian-pkm` | 📝 Obsidian | Obsidian・PKM・知識管理 |
| `dev-tools` | 🛠️ 開発ツール | AI駆動開発・プログラミング |
| `no-code` | 🔌 ノーコード | ノーコード・個人開発 |
| `efficiency` | ⚡ 業務効率化 | DX・ビジネス効率化 |
| `marketing` | 💰 マーケ/収益化 | Webマーケティング・マネタイズ |

---

## ローカル開発

```bash
cd C:\Users\moyam\OneDrive\ドキュメント\Obsidian保管庫\ai-navigator

# articles.json を手動再生成（GEMINI_API_KEY未設定の場合はトレンド翻訳がスキップされる）
python parse_news.py

# ローカルサーバー起動（file://ではfetchが動かないため必須）
python -m http.server 8765
# → http://localhost:8765 をブラウザで開く
```

## コミット手順（ローカル確認OK後）

```bash
# ① ai-navigator リポジトリ
cd ai-navigator
git add .
git commit -m "fix: ..."
git push origin main

# ② サブモジュール参照を保管庫側も更新（重要！忘れると古いコードがActionsで使われる）
cd ..
git add ai-navigator
git commit -m "chore: ai-navigator更新"
git push origin master
```

---

## まとめ

```
毎朝7時（JST）
  ↓ GitHub Actionsが自動起動（my-vaultリポジトリ）
  ↓ 一般AI記事を収集・要約 → Markdownとして保存
  ↓ 公式SDKリリースも収集（24hフィルター免除）
  ↓ パーソナルピックで優先度判定
  ↓ Markdown → articles.json に変換
  ↓ GitHub Trending も RSS から直取得・GitHub API補完・Gemini日本語翻訳
  ↓ ai-navigatorリポジトリのgh-pagesブランチへデプロイ
  ↓ Cloudflare Pagesが検知して自動公開
人が何もしなくても毎朝 AIニュース・公式リリース・GitHub Trending が更新される
```

---
title: AI Navigator 全自動デプロイフロー 解説
created: 2026-03-19
tags: [ai-navigator, github-actions, 解説]
---

# AI Navigator 全自動デプロイフロー 解説

図解: [[AI_Navigator_全自動フロー.drawio.png]]

---

## 概要

AI Navigatorは、毎朝7時（JST）に自動でAIニュースを収集・要約し、Webサイトとして公開するシステム。
人が何もしなくても、スケジュールに従って収集→要約→公開まで全自動で完結する。

---

## 登場するリポジトリ

| リポジトリ | 用途 |
|---|---|
| `suzutomo-organization/my-vault` | GitHub Actionsの実行場所。ニュース記事（Markdown）の保存先 |
| `suzutomo1984/ai-navigator` | Webサイトのソースコード置き場。gh-pagesブランチが公開先 |

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
- Zenn・Qiita・海外メディア等、複数のAI関連メディアのRSSフィードを巡回
- 24時間以内の記事のみを対象（古い記事は除外）
- URL重複を自動除外
- 収集した記事を Gemini API（`gemini-3-flash-preview`）に渡して日本語で自動要約

**Markdownファイル生成**
- 要約結果を1記事1ファイルのMarkdown形式に変換
- `自動ニュース配信/` フォルダに保存（ファイル名は日付ベース）

**my-vault masterへ保存**
- 生成されたMarkdownファイルを `suzutomo-organization/my-vault` のmasterブランチにコミット
- 変更がない場合はコミットをスキップ（無駄なコミット防止）
- GitHub Actions bot（`github-actions[bot]`）がコミット・プッシュを自動実行

---

### 3. ② パーソナルピック（personal-pick.yml）

① の完了を検知して自動的に起動（`workflow_run` トリガー）。

**実行スクリプト: `.github/scripts/personal_pick.py`**

**AI優先度スコアリング**
- デイリーノート（直近3日分）から友也の活動文脈を抽出
- キーワードスコアリング＋Gemini API（`gemini-3-flash-preview`）で記事を分析
- 「注目すべき記事か（isPick）」「優先度スコア（pickPriority）」を各記事に付与
- 3〜5記事の「必読ピック」として深い洞察・連鎖反応・未来予測を生成
- Gemini APIが503エラーの場合は最大3回・5秒間隔で自動リトライ
- スコアリング結果をMarkdownファイルに追記

**サイト表示データ整形**

**実行スクリプト: `ai-navigator/parse_news.py`**

- `自動ニュース配信/` フォルダのMarkdownファイルを全件解析
- 直近7日以内の記事にはボーナススコアを付与
- JavaScriptが読み込めるデータ形式（`articles.json`）に変換して出力

> **なぜJSONに変換するか？**
> WebサイトはMarkdownを直接読めない。JavaScriptがデータを取得・表示するためにJSON形式への変換が必要。

**AI Navigator専用リポジトリへデプロイ**
- `index.html` / `app.js` / `style.css` / `articles.json` を一時ディレクトリにまとめる
- `suzutomo1984/ai-navigator` リポジトリの `gh-pages` ブランチへforce pushで上書きデプロイ
- 毎回丸ごと上書きするため、履歴を残さないforce pushを使用（`git push --force`）
- デプロイ失敗してもワークフロー全体は止まらない（`continue-on-error: true`）

---

### 4. Cloudflare Pages（自動公開）

- `suzutomo1984/ai-navigator` の `gh-pages` ブランチを常時監視
- ブランチの変更を検知すると自動でビルド＆公開
- 公開URL: `ai-news-eev.pages.dev`

---

## まとめ

```
毎朝7時
  ↓ GitHub Actionsが自動起動（my-vaultリポジトリ）
  ↓ AIがニュースを収集・要約 → Markdownとして保存
  ↓ AIが記事の優先度を判定 → JSONに変換
  ↓ ai-navigatorリポジトリのgh-pagesブランチへデプロイ
  ↓ Cloudflare Pagesが検知して自動公開
人が何もしなくても毎朝最新ニュースが更新される
```

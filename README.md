# AI NEWS HUB

AI・自動化・開発ツール領域のニュースを自動収集し、ブラウザで閲覧できるパーソナルニュースリーダー。

**公開URL**: https://suzutomo1984.github.io/ai-news-hub/

---

## 概要

GitHubリポジトリ内の `自動ニュース配信/` フォルダに蓄積されたMarkdownニュース記事を、`parse_news.py` が `articles.json` に変換し、静的HTMLサイトとして配信する仕組み。

GitHub Actionsでパーソナルピック処理（`personal-pick.yml`）が完了するたびに自動更新される。

---

## 構成ファイル

```
ai-news-hub/
├── index.html        # メインUI（タブ：LATEST / PICKS / RANKING）
├── style.css         # スタイル
├── app.js            # フィルタ・検索・タブ切り替えロジック
├── parse_news.py     # Obsidian保管庫のMDを articles.json に変換するパーサー
├── articles.json     # パーサーの出力（自動生成・gitignore対象）
├── start.bat         # ローカル確認用サーバー起動スクリプト（Windows）
└── audit_report.txt  # parse_news.py の実行ログ
```

---

## アーキテクチャ

```
my-vault リポジトリ
└── 自動ニュース配信/*.md   ← AIが毎日生成するニュース記事
        ↓
    personal-pick.yml（GitHub Actions）
        ↓ parse_news.py を実行
    articles.json を生成
        ↓ git push（手動 or Actions）
    ai-news-hub リポジトリ（gh-pages ブランチ）
        ↓ GitHub Pages
    https://suzutomo1984.github.io/ai-news-hub/
```

### 2リポジトリ構成

| リポジトリ | 役割 |
|---|---|
| `suzutomo-organization/my-vault` | ニュース記事の生成・parse_news.pyの実行を担うメインリポジトリ |
| `suzutomo1984/ai-news-hub` | フロントエンド（HTML/CSS/JS）とarticles.jsonを管理。GitHub Pagesで配信 |

---

## カテゴリ

| カテゴリ | アイコン | 対象キーワード |
|---|---|---|
| AI/MCP | 🤖 | AIエージェント、LLM、Claude |
| Obsidian | 📝 | Obsidian、PKM、知識管理 |
| 開発ツール | 🛠️ | AI駆動開発、プログラミング、AIコーディング |
| ノーコード | 🔌 | Vibe Coding、個人開発 |
| 業務効率化 | ⚡ | DX、ビジネス |
| マーケ/収益化 | 💰 | Webマーケティング、個人開発マネタイズ |

---

## ローカル確認

```bash
# start.bat を実行（Pythonの http.server を起動）
start.bat

# ブラウザで確認
http://localhost:8000
```

---

## デプロイの仕組み

`personal-pick.yml`（my-vault リポジトリのGitHub Actions）の最後に以下が実行される：

1. `parse_news.py` を実行 → `articles.json` を生成
2. `suzutomo1984/ai-news-hub` リポジトリに push（PAT使用）
3. GitHub Pages が `gh-pages` ブランチから自動デプロイ

### 必要なSecrets（my-vaultリポジトリ側）

| Secret名 | 内容 |
|---|---|
| `AI_NEWS_HUB_DEPLOY` | `suzutomo1984/ai-news-hub` への書き込み権限を持つFine-grained PAT |

---

## 開発経緯

- **Phase 0（2026-03-18完了）**: ローカルMVP構築・動作確認
- **Phase 1（2026-03-18完了）**: GitHub Actions連携・GitHub Pages公開
- **Phase 2（今後）**: Cloudflare Pages移行検討・機能追加

---

## 関連リンク

- 公開サイト: https://suzutomo1984.github.io/ai-news-hub/
- リポジトリ: https://github.com/suzutomo1984/ai-news-hub

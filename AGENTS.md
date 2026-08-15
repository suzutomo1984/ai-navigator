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

このリポは my-vault の**サブモジュール**。本番配信は `gh-pages` ブランチ → Cloudflare Pages（https://ai-navigator.dev）。

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

### 3. mainに `push: main` トリガーのデプロイworkflowを復活させるな（過去の重大事故）
- **事故（2026-06-17）**: かつて `.github/workflows/deploy.yml` が `on: push: main` で `git push origin HEAD:gh-pages --force` を実行していた。これがPRマージのたびに発火し、**mainに残る古い `articles.json` で本番(gh-pages)を上書き**して、本番が繰り返し約2ヶ月前に巻き戻った（1日で3回発生）。
- **根治済み**: deploy.yml は**削除**し、`articles.json` は**gitignore**（自動生成物なのでmainで追跡しない）。フロント配信は my-vault の `personal-pick.yml` が完全に担う（html/js/css/articles.json をビルドして gh-pages に force push）。
- **禁止**: このリポに `on: push: main` で gh-pages を更新するworkflowを再追加すること。`articles.json` をmainにコミットすること（gitignore済み）。
- 「PRをマージしたら本番が古い日付になった」が再発したら、まず `push: main` トリガーのworkflowが復活していないか・articles.jsonがmainに混入していないか確認する。
- 本番(gh-pages)を手動で再生成したいときは my-vault で `gh workflow run auto-news.yml`（→ personal-pick が連鎖デプロイ）。

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

### 「修正したのに本番の見た目が変わらない」
→ **キャッシュと結論する前に実物を見て切り分けろ**（思い込みで「キャッシュ」と断定しない）。
- まず本番に修正が届いているか: `curl -sf "https://ai-navigator.dev/style.css?nc=$(date +%s)" | grep "<修正の目印>"`
- 届いている → ブラウザ/エッジのキャッシュ。スマホはシークレットタブ / `?v=xxx` 付きURL / サイトデータ削除で新版を確認。
- 届いていない → デプロイ未完了（Cloudflareビルド待ち20〜60秒）か、そもそも別カードが未修正（実機スクショ/動画のフレームを実際に見て、どのカードタイプが崩れているか特定する。CSSは `.paper-cell-onside`(サイド) と `.paper-cell-small`(メイン下段) で別物。片方直してももう片方は残る）。

---

## フロント（CSS / app.js / レスポンシブ）を改修したとき

`parse_news.py` ではなく見た目（HTML/CSS/JS）を触った場合の検証・反映手順。

### ローカル検証（本番に出す前に必ず）
1. **no-cache サーバーで配信**。`python -m http.server` はブラウザがキャッシュして古い版を掴むので不可。`Cache-Control: no-store` を返す簡易サーバーを別ポート（例8799）で立てる。
2. **本番同等データで確認**したいなら gh-pages の articles.json を落とす: `curl -sf "https://ai-navigator.dev/articles.json" -o articles.json`（gitignore対象なのでコミットされない）。
3. **レスポンシブ確認は Playwright CLI を使う**（Claude-in-Chrome は viewport が効かず `@media` が発火しない）。
   ```bash
   playwright-cli open && playwright-cli resize 390 844   # スマホ幅
   playwright-cli goto "http://localhost:8799/?v=test"
   playwright-cli eval "getComputedStyle(...).flexDirection" # 計測
   playwright-cli screenshot --filename=check.png            # 見た目も必ず目視
   ```
4. **数値（getComputedStyle）だけで判断しない**。向き・左右配置のミスは数値に出ない（例: `order` 忘れでサムネが左右逆になる。サイドカードは `body=order:1 / thumb=order:2` でサムネを右に置いている）。スクショで実際の見た目を確認する。
5. **友也（ユーザー）にもローカルで確認してもらい、OKが出てから本番へ**。

### 本番反映（必ずユーザーの明示GOを取ってから実行）
本番への push / デプロイは「OK / 反映して」を取ってから。確認なしで反映しない。
1. `git add <file> && git commit && git push origin HEAD:main`（このリポ ai-navigator）
2. 新SHAがリモートに在るか確認: `gh api repos/suzutomo1984/ai-navigator/commits/<sha> --jq '.sha'`（未pushのSHAを親が参照するとCIが `not our ref` で死ぬ）
3. my-vault でサブモジュール参照更新 → commit → `git pull --rebase origin master && git push`
4. `gh workflow run 229227365`（personal-pick）→ gh-pages へデプロイ → Cloudflare が自動ビルド（20〜60秒）
5. 反映確認: personal-pick の success、gh-pages のデプロイ時刻、本番 Cloudflare に curl で修正が届いたか、を確認（緑だけ信じない）。

---

## 変更後に必ず確認すること
- [ ] `python -c "import py_compile; py_compile.compile('parse_news.py', doraise=True)"` が通る
- [ ] ローカル生成で記事数・最新日付が想定通り（前回から激減していないか）
- [ ] サムネ率が大きく落ちていないか（OGP関連を触った場合）
- [ ] カテゴリを足したなら上記「3点同期」が揃っているか
- [ ] フロント（CSS/JS/HTML）を触ったなら、Playwright で PC幅・スマホ幅(390px)の両方をスクショ目視したか
- [ ] 本番反映は、ユーザーの明示GOを取ってから実行したか（確認なしで本番に出さない）

# AI Navigator 手順書

AI Navigator は、AI と業務効率化のニュースを毎日2回自動で集めて載せるサイトです。
本番は https://ai-navigator.dev です（Cloudflare Pages が配信）。
コードはこのフォルダ（GitHub の `suzutomo1984/ai-navigator`、ブランチ `main`）にあります。
収集と配信の自動処理は、保管庫のリポジトリ（`suzutomo-organization/my-vault`）の GitHub Actions が動かします。
本番の中身は `suzutomo1984/ai-navigator` の `gh-pages` ブランチです。`main` に push しただけでは本番は変わりません。

**この手順書が正本です。** AI が守る約束事は [AGENTS.md](AGENTS.md) にあります。作業の前に両方を読んでください。

| やりたいこと | 読む節 |
|---|---|
| 記事（/articles/）を公開する | [① 記事を出す](#-記事を出す) |
| 公開した記事を Google に知らせる | [①-3 Google に知らせる](#1-3-google-に知らせる) |
| 見た目や動きを直す・手元で確かめる | [② サイトを直す](#-サイトを直す) |
| 直したものを本番に出す | [③ 本番に出す](#-本番に出す) |
| いつ何が自動で動くかを知る | [④ 自動の流れ](#-自動の流れ) |
| 本番が更新されない・表示がおかしい | [⑤ 困ったとき・落とし穴](#-困ったとき落とし穴) |

コマンドはすべて、この PC（Windows）の PowerShell で打つ前提です。
フォルダの場所は `C:\Users\suzuki.tomoya\Documents\Obsidian保管庫\ai-navigator` です（以下「このフォルダ」）。

---

## ① 記事を出す

記事は https://ai-navigator.dev/articles/ に並ぶ読み物です（2026-10-31 に1本目を公開）。
原稿の書き方は [posts/_README.md](posts/_README.md) にあります。**原稿の書き方はそちらが正本です。ここには写しません。**
`posts/_README.md` は友也向けの説明書です。KURO は中身を書き換えません。

### 1-1. 仕組み（KURO が知っておくこと）

- 原稿は `posts/<名前>.md` です。名前が `_` で始まるファイルは記事になりません。
- `build_articles.py` が原稿から HTML を作ります。出力先は `articles/` です（git では追跡しない生成物）。
- 引数なしで動かすと、下書きも含めて作ります。`sitemap.xml` と `llms.txt` には触りません。
- `--publish` を付けると、公開日（`published:`）が今日（日本時間）以前の記事だけを作ります。あわせて `sitemap.xml` と `llms.txt` に記事を書き足します。
- **`--publish` は配信の自動処理（④）が本番で動かします。手元では打ちません。** 手元で打つと、git で追跡している `llms.txt` が書き換わります。
- 本番に出るのは、`published:` が今日以前の記事だけです。未来の日付なら、その日の配信まで出ません。
- 写真は `assets/` に `.webp` で置きます。本文からは `/assets/<名前>.webp` で参照します。**配信は `assets/*.webp` しかコピーしません。** `.png` や `.jpg` は本番に出ません。
- 友也は `記事プレビュー.bat` で自分で原稿を直して確かめます（中身は `preview_articles.py`。下書きモードで作り直し、`http://127.0.0.1:8080/articles/` を開く）。

### 1-2. KURO がやる公開の作業

友也から「〇〇の記事を公開して」と言われたら、上から順にやります。

1. 原稿の頭の設定を確かめる。`slug`・`title`・`checked`・`published` が入っているか。`published` が今日以前か。
   ```powershell
   cd C:\Users\suzuki.tomoya\Documents\Obsidian保管庫\ai-navigator
   Select-String -Path posts\<名前>.md -Encoding UTF8 -Pattern '^(slug|title|published|checked):'
   ```
2. 本文が参照する写真が `assets/` に `.webp` であるか確かめる。
   ```powershell
   Select-String -Path posts\<名前>.md -Encoding UTF8 -Pattern '/assets/'
   ```
3. 手元で作れるか確かめる（下書きモード。`articles/` だけが変わる）。エラーが出たら、出た行を友也に伝えて止まる。
   ```powershell
   python build_articles.py
   ```
4. 友也に「この内容で本番に出してよいか」を聞き、**「OK」をもらう。**
5. 原稿と写真だけを commit して push する。今いるブランチが `main` であることを先に確かめる。
   ```powershell
   git branch --show-current   # main と出ること
   git status --short
   git add posts\<名前>.md assets\<写真>.webp
   git commit -m "feat: 記事「<タイトル>」を公開"
   git push origin HEAD:main
   ```
6. [③ 本番に出す](#-本番に出す) の手順 4〜8 をやる（配信を走らせて、届いたかを確かめる）。
7. 本番で記事が出たことを確かめる。タイトルが原稿と同じなら届いている。
   ```powershell
   $nc = [DateTimeOffset]::Now.ToUnixTimeSeconds()
   $page = Invoke-WebRequest "https://ai-navigator.dev/articles/<slug>?nc=$nc" -UseBasicParsing
   [regex]::Match($page.Content, '<title>[^<]*</title>').Value
   ([regex]::Matches((Invoke-WebRequest "https://ai-navigator.dev/sitemap.xml?nc=$nc" -UseBasicParsing).Content, '<loc>[^<]*articles[^<]*</loc>')).Value
   ```
   存在しないパスも `200` で TOP の HTML が返ります。**状態コードではなく、タイトルで判断します。**
8. 次の「1-3. Google に知らせる」をやる。

### 1-3. Google に知らせる

記事が本番に出たら、2つのことをします。

**(1) サイトマップを送り直す（API で送れる）**

- Search Console API の `PUT /webmasters/v3/sites/{site}/sitemaps/{feed}` を使います。成功すると `204` が返ります（2026-10-31 実測。`.agents/memory/reference_agent_browser_usage.md`）。
- 鍵は GSC MCP の設定（`~/.claude.json` の `mcpServers.google-search-console.env`）にある `GOOGLE_CLIENT_ID`・`GOOGLE_CLIENT_SECRET`・`GOOGLE_REFRESH_TOKEN` です。この鍵には書き込みの権限が付いています。
- 鍵の値は画面にもファイルにも出しません。
- `{site}` は `sc-domain:ai-navigator.dev` です（ドメイン単位のプロパティ。2026-08-15 のメモリ `project_ai_navigator_domain_migration.md`）。
- `{feed}` はフルURL `https://ai-navigator.dev/sitemap.xml` です。ドメイン単位のプロパティでは、パスだけだと「サイトマップ アドレスが無効です」で弾かれます。

```powershell
# 2026-10-31 に KURO がこのまま走らせて 204 を確認
$cfg = (Get-Content "$HOME\.claude.json" -Raw | ConvertFrom-Json).mcpServers.'google-search-console'.env
$tok = Invoke-RestMethod -Method Post 'https://oauth2.googleapis.com/token' -Body @{
  client_id = $cfg.GOOGLE_CLIENT_ID; client_secret = $cfg.GOOGLE_CLIENT_SECRET
  refresh_token = $cfg.GOOGLE_REFRESH_TOKEN; grant_type = 'refresh_token' }
$site = [uri]::EscapeDataString('sc-domain:ai-navigator.dev')
$feed = [uri]::EscapeDataString('https://ai-navigator.dev/sitemap.xml')
$url  = "https://www.googleapis.com/webmasters/v3/sites/$site/sitemaps/$feed"
(Invoke-WebRequest -Method Put $url -Headers @{ Authorization = "Bearer $($tok.access_token)" } -UseBasicParsing).StatusCode   # 204 なら成功
(Invoke-RestMethod $url -Headers @{ Authorization = "Bearer $($tok.access_token)" }).lastSubmitted   # 送った時刻（UTC。日本時間は +9 時間）
```

**(2) 記事の URL の「インデックス登録をリクエスト」を押す（画面でしかできない）**

- この操作には API がありません。AI 用ブラウザ agent-browser の `kuro` セッションで、Search Console の画面から押します。
- `kuro` のプロファイルは Google（suzuki.tomoya@smart2j.com）にログイン済みです（2026-10-31）。
- **GSC MCP の `submit_url_for_indexing` は使いません。** これは別の API（Indexing API）で、このサイトでは失敗します。
- `/search-console/inspect?…` の直リンクは 404 になります。URL 検査の入力欄から入れます。

```powershell
$prof = 'C:\Users\suzuki.tomoya\.agent-browser\profiles\kuro'
# 2026-10-31 にこの URL で ai-navigator.dev のサマリーが開くことを確認
agent-browser --session kuro --profile $prof --headed open 'https://search.google.com/search-console?resource_id=sc-domain%3Aai-navigator.dev'
agent-browser --session kuro snapshot -i                 # 上部の「URL検査」入力欄の ref（@eNN）を探す
agent-browser --session kuro fill '@eNN' 'https://ai-navigator.dev/articles/<slug>'
agent-browser --session kuro press Enter
agent-browser --session kuro snapshot -i                 # 「インデックス登録をリクエスト」の ref を探す
agent-browser --session kuro click '@eNN'
```

- PowerShell では `@eNN` を引用符で囲みます。
- ログインが切れていたら、`--headed` の画面で友也にログインしてもらいます。パスワードは KURO が入れません。

---

## ② サイトを直す

### 2-1. 主なファイル

| ファイル | 役割 |
|---|---|
| `index.html` | TOP（`/`）。今日の重要4本・最新ニュース・統計 |
| `news.html` | ニュース一覧（`/news`） |
| `official.html` / `official.js` | リリースノート（ツールの更新情報） |
| `about.html` / `privacy.html` | このサイトについて／プライバシー |
| `app.js` / `style.css` | 全ページ共通の動きと見た目 |
| `parse_news.py` | 保管庫の `自動ニュース配信/*_テックニュース.md` から `articles.json` を作る。TOP などの数字も書き換える |
| `daily/morning_edition.py` | 朝刊（`/daily/`）を作る |
| `build_articles.py` / `posts/` | 記事（`/articles/`）を作る |
| `_headers` / `_redirects` / `llms.txt` / `robots.txt` / `sitemap.xml` | Cloudflare の設定と、検索エンジン・AI 向けの案内 |

`articles.json`・`articles/`・`sitemap.xml`・`robots.txt` は自動生成物です。git では追跡しません（`.gitignore`）。

### 2-2. 手元で確かめる

本番と同じデータで見るのが基本です。**`parse_news.py` は手元では走らせません。**
手元で走らせると、git で追跡している `index.html`・`news.html`・`official.html`・`about.html` の数字が書き換わります。しかも手元の md が古いので、数字も古くなります。

1. 本番の `articles.json` を落とす（`.gitignore` 済みなので commit されない）。
   ```powershell
   cd C:\Users\suzuki.tomoya\Documents\Obsidian保管庫\ai-navigator
   Invoke-WebRequest 'https://ai-navigator.dev/articles.json' -OutFile articles.json -UseBasicParsing
   ```
2. キャッシュしないサーバーを立てる（別の窓で動かし続ける）。
   ```powershell
   python daily\preview_server.py --root . --port 8799
   ```
   - `http://127.0.0.1:8799/` で TOP が開きます。
   - 普通の `python -m http.server` は使いません。ブラウザが古いファイルを掴みます。
   - `start.bat` も使いません。中で `parse_news.py` を走らせます。
3. 朝刊を手元で作って見たいときは、次を使います（初回だけ `npm ci`）。`AI_GATEWAY_API_KEY` と `GEMINI_API_KEY` が要ります。
   ```powershell
   npm ci
   python daily\local_preview.py
   ```
   本番の `articles.json` から今日の朝刊を作り、`http://127.0.0.1:8799/` で表示します。

### 2-3. スマホ幅で確かめる

スマホ幅は Playwright CLI（`playwright-cli`）で見ます。Claude in Chrome は画面幅を変えても CSS の `@media` が効きません。

```powershell
playwright-cli open
playwright-cli resize 390 844
playwright-cli goto "http://127.0.0.1:8799/?v=test"
playwright-cli eval "window.matchMedia('(max-width: 768px)').matches"   # true ならスマホ幅で見えている
playwright-cli screenshot --filename=check-390.png
playwright-cli resize 1280 900
playwright-cli screenshot --filename=check-1280.png
playwright-cli close
```

- **数字だけで判断しません。** スクショを開いて見ます。左右の入れ替わりなどは数字に出ません。
- 終わったら、友也にも `http://127.0.0.1:8799/` で見てもらいます。

### 2-4. 直したあとに確かめること

- [ ] `git status --short` に、自分が直したファイルだけが出ている（`parse_news.py` や `build_articles.py --publish` で書き換わったファイルが混ざっていない）
- [ ] `parse_news.py` を直したら `python -c "import py_compile; py_compile.compile('parse_news.py', doraise=True)"` が通る
- [ ] テストがあるものは走らせる（`tests/` に `test_*.py` と `*_regression.mjs` がある）
- [ ] 見た目を直したら、PC 幅とスマホ幅（390px）のスクショを両方見た
- [ ] 友也が手元で見て「OK」と言った

---

## ③ 本番に出す

**本番に出すのは、友也の「OK」「反映して」をもらってからです。** 「何を入れるか」の確認と「出してよいか」の確認は別です。

### 3-1. 手順

1. このフォルダで、出すものだけを commit する。最初に、今いるブランチが `main` であることを確かめる（手順 2 は今のブランチの中身を `main` に送るため）。
   ```powershell
   cd C:\Users\suzuki.tomoya\Documents\Obsidian保管庫\ai-navigator
   git branch --show-current   # main と出ること
   git status --short
   git add <ファイル>
   git commit -m "fix: <何を直したか>"
   ```
2. `main` に push する。
   ```powershell
   git push origin HEAD:main
   ```
3. push が届いたか確かめる。2つの値が同じならよい。
   ```powershell
   git fetch origin
   git rev-parse HEAD origin/main
   ```
4. 配信（パーソナルピック）を手で走らせる。走らせる直前の時刻（UTC）を控えておく。
   ```powershell
   $start = (Get-Date).ToUniversalTime(); $start
   gh workflow run personal-pick.yml --repo suzutomo-organization/my-vault --ref master
   ```
   - 手で走らせると、SNS への投稿はしません（入力 `post_sns` の既定が false）。
   - 朝刊は、その日の号が本番に無いときだけ作ります。作り直すなら `-f generate_morning=true` を足します。
   - 自動の配信が動いている最中なら、終わるまで待ってから動きます（同時には動かない）。
5. 数秒待ってから実行の番号を取り、終わるまで待つ。すぐに一覧を見ると、前回の実行が出ることがある。開始時刻が手順 4 の時刻より後の行を選ぶ。
   ```powershell
   gh run list --repo suzutomo-organization/my-vault --workflow personal-pick.yml --limit 1
   gh run watch <番号> --repo suzutomo-organization/my-vault --exit-status
   ```
6. `gh-pages` が書き換わったか確かめる。時刻は UTC です。手順 4 で控えた `$start` より後なら書き換わっています。
   ```powershell
   gh api "repos/suzutomo1984/ai-navigator/commits?sha=gh-pages&per_page=1" --jq '.[0].commit.author.date'
   ```
   **実行が success でも、配信の段だけ失敗していることがあります**（配信の段は失敗しても全体を止めない設定）。だからこの確認を飛ばしません。
7. Cloudflare が `gh-pages` から作り直すのを待つ（20〜60秒ほど）。
8. 本番に届いたかを、本文で確かめる。直した箇所に固有の文字列を探します。
   ```powershell
   $nc = [DateTimeOffset]::Now.ToUnixTimeSeconds()
   (Invoke-WebRequest "https://ai-navigator.dev/style.css?nc=$nc" -UseBasicParsing).Content -match '<直した箇所の目印>'
   ```
9. 友也にスマホでも再読み込みして見てもらう。

### 3-2. 保管庫側のこと

- 配信は、ai-navigator の `origin/main` をその場で clone して使います（`personal-pick.yml` 96〜106行）。保管庫のサブモジュール参照（gitlink）は見ていません。
- だから**サブモジュール参照の更新は、本番に出すためには要りません。** 保管庫の `git status` に `M ai-navigator` が出ても、配信には効きません。整えたいときだけ commit します。
- 逆に、`.github/workflows/*.yml` や `.github/scripts/*.py` を変えたときは、**保管庫（my-vault）の `master` に push しないと効きません。** 保管庫には bot の commit が頻繁に入るので、push の前に取り込みます。
  ```powershell
  cd C:\Users\suzuki.tomoya\Documents\Obsidian保管庫
  git pull --rebase origin master
  git push origin master
  ```

### 3-3. 新しいファイルを本番に出すとき

配信は、決まったファイルしか本番にコピーしません（`personal-pick.yml` 284行の一覧と 297〜330行の `cp`）。
新しいファイルを本番に出すには、保管庫の `personal-pick.yml` の**2か所（存在を確かめる一覧と `cp`）に足して**、保管庫に push します。
片方だけだと、配信が止まるか、本番に出ません。
例外として、`assets/*.webp`・`articles/*.html`・`daily/` はまとめてコピーされます。

---

## ④ 自動の流れ

すべて保管庫（`suzutomo-organization/my-vault`）の GitHub Actions です。時刻は日本時間です。

| いつ | ワークフロー（ファイル） | すること |
|---|---|---|
| 毎日 05:00 と 15:45 | 自動ニュース配信（`.github/workflows/auto-news.yml`） | RSS を集めて Gemini で要約し、`自動ニュース配信/YYYY-MM-DD_テックニュース.md` を作って保管庫に commit する |
| 上が成功した直後 | パーソナルピック（`.github/workflows/personal-pick.yml`、ID `229227365`） | ピックを作り、`articles.json`・朝刊・記事を作って `gh-pages` に配信する |
| `gh-pages` が変わったとき | Cloudflare Pages | `gh-pages` から本番を作り直す |

- GitHub の都合で、予定の時刻より遅れて動くことがあります。
- 同じ日の同じ回（朝・夕）は、2回目以降は収集しません（台帳 `.github/state/news_delivery.json`）。収集しなかった回は、パーソナルピックも配信しません。
- 手で走らせたパーソナルピックは、台帳に関係なく配信します。

### パーソナルピックの中身（上から順に）

1. ai-navigator の `origin/main` を clone する。
2. `.github/scripts/personal_pick.py` が `自動ニュース配信/YYYY-MM-DD_パーソナルピック.md` を作る。スプレッドシートにも写す。保管庫に commit する。
3. 本番の前回分 `articles.json` を `gh-pages` から取る（サムネや初出時刻を引き継ぐため）。
4. 本番の前回分 `daily/` を `gh-pages` から取る。取れなければ配信を止める（朝刊を失わないため）。
5. `parse_news.py` が `articles.json` を作り直す。`index.html`・`news.html`・`official.html`・`about.html` の数字や一覧と、`sitemap.xml`・`robots.txt` も書き換える。`index.html` の目印（`TOP_STATS_BAR` などの `<!-- 名前:start -->`）が欠けていると、エラーで止まる。
   - 記事数が前回の7割を切ったら、終了コード 42 で止まり、配信しない（古い本番を守るため）。
6. **朝刊は、その日の号（`daily/YYYY-MM-DD-am.html`）が本番に無いときだけ作る。** 作らない回は、前回の `daily/` をそのまま使う。
   - 朝刊を作れなかったら Slack に知らせ、サイト本体の配信は続ける。
   - 過去の号は本文を作り直さない。作った回に、前後の号へのリンクだけ更新される（`daily/morning_edition.py` 626行付近）。
7. `build_articles.py --publish` が記事ページを作り、`sitemap.xml` と `llms.txt` に足す。失敗したら前回の記事ページを使い、配信は続ける。
8. 決まったファイルを1つのフォルダに集め、`gh-pages` に force push する。
9. 朝刊を作った回は、朝刊を X / Threads に投稿する（Buffer 経由。号ごとに1回）。
10. 更新のお知らせを X / Threads に投稿する（回ごとに1回）。

### 本番に出るもの

`index.html`・`news.html`・`app.js`・`style.css`・`official.html`・`official.js`・`about.html`・`privacy.html`・`AI_Navigator_全自動フロー.drawio.png`・`articles.json`・`_headers`・`sitemap.xml`・`robots.txt`・`_redirects`・`llms.txt`・`assets/*.webp`・`articles/*.html`・`daily/`。

`ai-consult.js` は、HTML から読んでいますが本番には出していません（2026-10-31 にも本番で `text/html` が返るのを確認）。AI 相談ボタンは本番では動いていません。

### articles.json のおもな中身

- 全体: `generatedAt`・`latestBatchAt`（一番新しい配信の時刻）・`totalArticles`・`dates`・`categories`・`articles`・`trending` など
- 記事1本: `id`・`date`・`title`・`url`・`source`・`category`・`summary`・`isPick`・`isOfficial`・`addedAt`（初めて載った時刻。引き継がれる）・`thumbnail` など
- NEW の札は、`addedAt` が `latestBatchAt` と同じ記事に付きます。

### カテゴリ

`official`（リリースノート）・`sales-marketing`・`back-office`・`productivity`・`strategy`・`info-mgmt`・`ai-tech`・`side-business`・`other`。
分類は、Gemini が出す md の `##` 見出しで決まります。足し方は [AGENTS.md](AGENTS.md) の約束事 2 にあります。

---

## ⑤ 困ったとき・落とし穴

| 症状 | まず見ること | 理由 |
|---|---|---|
| 本番が古い日付のまま | パーソナルピックの実行結果（自動ニュース配信ではなく） | 配信するのはパーソナルピックです。自動ニュース配信が成功でも、配信は別です |
| パーソナルピックは success なのに本番が古い | ③の手順 6（`gh-pages` の時刻）と、実行ログの `記事数激減ガード` `parse_news.py 実行失敗` | 配信の段は失敗しても全体を success にします |
| 記事数が激減したと止まった | `$env:OGP_BUDGET_SEC='0'; python parse_news.py` を手元で走らせ、最新日付が出るか（終わったら `Remove-Item Env:OGP_BUDGET_SEC` と、[AGENTS.md](AGENTS.md) の約束事 4 のとおり書き換わったファイルを戻す） | 2026-06-17、サムネ取得が遅すぎて書き出し前に止まったことがあります |
| 直したのに見た目が変わらない | ③の手順 8 で本番の本文に届いているか | 届いていればブラウザのキャッシュです。届いていなければ配信がまだか、直した場所が違います |
| 本番の URL が `200` を返すのにおかしい | `Content-Type` と本文 | 存在しないパスにも、TOP の HTML が `200` で返ります |
| Python から本番を叩くと `403` | User-Agent を変える | Cloudflare が `Python-urllib` を弾きます。PowerShell と curl は通ります（2026-08-12 の観察。今回は PowerShell で通ることだけ確かめた） |
| 新しいファイルが本番に無い | `personal-pick.yml` の一覧 | ③の 3-3 のとおり、決まったファイルしか出ません |
| 記事の写真が本番に出ない | 拡張子 | `assets/*.webp` しか出ません |
| 朝刊のテンプレートを直したのに変わらない | その日の号がもう本番にあるか | 朝刊は、その日の号が無い回にしか作り直しません。`generate_morning=true` で手で走らせます |
| 古い号やファイルを消したのに URL が開く | 本文が TOP の HTML ではないか | Cloudflare は過去に配信したファイルを返し続けることがあります（2026-08-08 の観察。今回は未確認）。消すなら `_redirects` などで対処します |
| 旧ドメインで開かれる | — | 旧 `ai-news-eev.pages.dev` は、各 HTML の頭の JS で新ドメインへ移ります（`pages.dev` では 301 を設定できない） |

---

## 最終確認日 2026-10-31

この日に実物で確かめたもの:

- `.github/workflows/personal-pick.yml`（保管庫）: 起動条件、`submodules: false` と `origin/main` の clone（77・96〜106行）、配信の段の `continue-on-error`（170行）、朝刊の判定（205〜221行）、記事生成（268〜281行）、配信ファイルの一覧（284行）と `cp`（297〜330行）、SNS の段と `post_sns` の扱い（429〜499行）。`origin/master` と同じ（`78fe473e` まで）
- `.github/workflows/auto-news.yml`（保管庫）: cron `0 20 * * *`（05:00）と `45 6 * * *`（15:45）
- `.github/scripts/news_delivery.py` の `cmd_gate_deploy`（291〜323行）と `cmd_morning_decision`（376〜387行）
- `gh workflow list`: パーソナルピックの ID `229227365`。`gh run list`: 10-31 の実行はすべて success
- `gh api` で `gh-pages` の中身（`articles/`・`daily/`・`assets/` あり、`trending.html` なし）と最終配信時刻（2026-10-31 13:10 UTC）
- 本番: `/`・`/articles/`・`/articles/bitwarden-to-1password`・`/daily/` が `200`、`Server: cloudflare`。`sitemap.xml` に記事2件。`/ai-consult.js` は `text/html`
- 本番の `articles.json` の項目名とカテゴリ
- `build_articles.py`（202〜258行）、`preview_articles.py`、`記事プレビュー.bat`、`daily/preview_server.py`、`daily/local_preview.py`
- `parse_news.py`: 書き込むファイル（29〜37行）、激減ガード（633〜647行）、環境変数 `OGP_BUDGET_SEC`・`OGP_WORKERS`、`CATEGORY_MAP`（65〜74行）
- `app.js` の `CAT_LABELS`（269行）。`ai-navigator/.github/workflows/` は `probe-release-notes.yml`（手動起動・読み取りのみ）だけ
- `playwright-cli --help` と `agent-browser --help` のコマンド名

- 1-3 のサイトマップ送信スニペット（そのまま走らせて `204`）、Search Console を開く URL、`sc-domain:ai-navigator.dev`（KURO が実行して確認）

確かめていないもの: ⑤の「Python から叩くと 403」「消したファイルを返し続ける」（どちらも過去の観察。表の中に書いた）。

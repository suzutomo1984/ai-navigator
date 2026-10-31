# AGENTS.md — AI が守る約束事

このリポジトリ（ai-navigator）を触る AI（Claude / Codex など）は、**作業の前にこのファイルと [README.md](README.md) を読んでください。**
手順は README.md にあります。ここには「やってはいけないこと」と「必ずやること」だけを、過去の事故の理由と一緒に書きます。

最終確認日: 2026-10-31（各項目の「確認」に、何を見て今も当たっていると判断したかを書いた）

---

## 1. 本番に出すのは、友也の「OK」をもらってから

- 本番への push と配信の実行は、友也の「OK」「反映して」をもらってからやる。
- 「何を入れるか」の確認を、「出してよいか」の確認と取り違えない。
- 理由: 2026-06-28、確認を取らずに本番へ出して指摘された。
- 手順: README の [③ 本番に出す](README.md#-本番に出す)

## 2. 本番に出たかは、本文で確かめる。緑や `200` を信じない

- パーソナルピックの実行が success でも、配信の段だけ失敗していることがある。配信の段は `continue-on-error: true` だから。
- 本番の URL は、存在しないパスにも TOP の HTML を `200` で返す。
- だから「`gh-pages` の最終時刻」と「本番の本文に直した箇所があるか」で確かめる。
- 理由: 2026-06-22、push が弾かれたのに気づかず配信し、古い版を本番に出した。2026-08-12、`200` で返った HTML をデータと取り違えた。`ai-consult.js` は今も `200` だが中身は HTML で、本番では動いていない。
- 確認: `personal-pick.yml` 170行（`continue-on-error: true`）。2026-10-31 に本番 `/ai-consult.js` が `text/html` で返ることを確かめた。
- 手順: README の [③ 3-1 の手順 6〜8](README.md#3-1-手順)

## 3. `main` への push で `gh-pages` を書き換えるワークフローを作らない。`articles.json` を commit しない

- このリポジトリに `on: push: main` で `gh-pages` を更新するワークフローを足さない。
- `articles.json` は `.gitignore` 済み。`main` に入れない。
- 理由: 2026-06-17、昔の `deploy.yml` が PR をマージするたびに `main` の古い `articles.json` で本番を上書きし、本番が約2か月前に1日3回巻き戻った。`deploy.yml` を消し、`articles.json` を `.gitignore` に入れて根治した。
- 本番を作るのは保管庫の `personal-pick.yml` だけ。
- 確認: `.github/workflows/` には `probe-release-notes.yml`（手動起動・読み取りのみ）しかない。`.gitignore` に `articles.json` がある。

## 4. `parse_news.py` と `build_articles.py --publish` を手元で走らせたら、書き換わったファイルを commit しない

- `parse_news.py` は、git で追跡している `index.html`・`news.html`・`official.html`・`about.html` を書き換える。手元の md は古いので、数字も古くなる。
- `build_articles.py --publish` は、git で追跡している `llms.txt` を書き換える。
- 手元で確かめるときは、本番の `articles.json` を落として使う。
- 走らせてしまったら、commit の前に `git status --short` を見て、自分が直していないファイルを `git checkout -- <ファイル>` で戻す。
- 理由: 2026-08-12、手元で走らせた TOP の記事数が 34本、本番は 57本だった。
- 確認: `parse_news.py` 29〜37行・772行・824〜825行・881行、`build_articles.py` 231〜232行。
- 手順: README の [② 2-2](README.md#2-2-手元で確かめる)

## 5. 新しいファイルを本番に出すときは、`personal-pick.yml` の2か所に足す

- 配信は、決まったファイルしか本番にコピーしない。
- 足すのは、存在を確かめる一覧（284行）と `cp`（297〜330行）の2か所。片方だけだと、配信が止まるか、本番に出ない。
- `personal-pick.yml` は保管庫（my-vault）にある。足したら保管庫の `master` に push しないと効かない。
- 例外: `assets/*.webp`・`articles/*.html`・`daily/` はまとめてコピーされる。写真は `.webp` にする。
- 理由: 2026-08-20、`ai-consult.js` を一覧に入れ忘れ、AI 相談ボタンが本番で一度も動いていなかった。
- 確認: `personal-pick.yml` 284・297〜330行。

## 6. OGP サムネの取得は並列のままにする

- `parse_news.py` のサムネ取得は `ThreadPoolExecutor` で並列にしている（環境変数 `OGP_WORKERS`、既定 20）。直列に戻さない。
- `OGP_BUDGET_SEC`（既定 600秒。0 で新しい取得を止める）を極端に小さくして、サムネを大量に飛ばさない。サムネは原則全部出す。
- 理由: 2026-06-17、直列で取っていたため書き出しの前に Actions が打ち切られ、本番が約2か月前の日付で止まった。Actions は success のままだった。
- 切り分け: `$env:OGP_BUDGET_SEC='0'; python parse_news.py` を走らせて、最新の日付が出れば犯人は OGP（終わったら `Remove-Item Env:OGP_BUDGET_SEC` と、約束事 4 のとおり戻す）。
- 確認: `parse_news.py` 592〜593行・610行。

## 7. カテゴリを足すときは3か所をそろえる

- 分類を決めるのは、Gemini が出す md の `##` 見出しだけ。`auto_news.py` の SOURCES にある `category` は分類に使われない。
- 足すときにそろえる3か所:
  1. 保管庫 `.github/scripts/auto_news.py`: SOURCES に収集元を足し、Gemini への指示の出力形式に `## 絵文字 カテゴリ名` を足す
  2. このリポジトリ `parse_news.py`: `CATEGORY_MAP` に `(id, 表示名, 絵文字, [キーワード])` を1行足す
  3. このリポジトリ `app.js`: `CAT_LABELS` に `"id": "【読者向けの言い換え】"` を足す（無いと「【今週の話題】」になる）
- 理由: 1か所でも抜けると、分類されないか、表示が浮く（2026-06-17 に副業カテゴリを足したときに確立）。
- 確認: `parse_news.py` 65〜74行、`app.js` 269〜279行・531行、`auto_news.py` 1954〜1968行（Gemini に渡すのはソース名・タイトル・URL・本文で、`category` は渡していない）と 2125〜2171行の `##` 見出し。旧版の `CAT_COLORS` は今の `app.js` に無い。

## 8. `index.html` などの目印を消さない

- `parse_news.py` は `<!-- 名前:start -->` 〜 `<!-- 名前:end -->` の間を書き換える。
- 今ある目印: `index.html` の `JSON_LD`・`TOP_STATS_BAR`・`TOP_STATS_COUNT`、`news.html` の `NEWS_ARTICLE_COUNT`、`official.html` の `OFFICIAL_ARTICLE_COUNT`。
- 目印が欠けると `parse_news.py` がエラーで止まり、その回は配信されない。
- 確認: `index.html` 50・179・219行、`news.html` 161行、`official.html` 158行、`parse_news.py` 720〜733行。

## 9. `articles.json` を直接書き換えない

- `articles.json` は毎回、保管庫の `自動ニュース配信/*.md` と `parse_news.py` から作り直される。直接直しても次の配信で元に戻る。
- 直すなら `parse_news.py` か元の md を直す。
- 理由: 2026-06-28 のリリースノート再設計で確かめた（メモリ `project_ai_navigator.md`）。今回は実物で再確認していない。

## 10. `posts/_README.md` は友也に確かめてから直す。中身を README に写さない

- 友也向けの記事の書き方の説明書。友也が自分で読んで原稿を直すためのもの。
- 直すのは、友也が頼んだときか、友也に確かめてから（例: 2026-10-31、公開後に Google に知らせる手順を友也の OK で足した）。
- README からはリンクを張るだけにして、中身を写さない。写すと2か所の食い違いが起きる。
- 記事の公開手順で KURO がやることは README の [① 記事を出す](README.md#-記事を出す) にある。

---

## 変更したあとに確かめること

- [ ] `git status --short` に、自分が直したファイルだけが出ている（約束事 4）
- [ ] `parse_news.py` を直したら `python -c "import py_compile; py_compile.compile('parse_news.py', doraise=True)"` が通る
- [ ] サムネに触ったら、サムネの割合が大きく落ちていない（約束事 6）
- [ ] カテゴリを足したら、3か所がそろっている（約束事 7）
- [ ] 見た目を直したら、PC 幅とスマホ幅（390px）のスクショを両方見た（README の [② 2-3](README.md#2-3-スマホ幅で確かめる)）
- [ ] 本番に出す前に、友也の「OK」をもらった（約束事 1）

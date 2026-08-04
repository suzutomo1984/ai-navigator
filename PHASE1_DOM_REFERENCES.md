# Phase 1: app.js DOM参照一覧

調査対象: `app.js` 全体の `getElementById` / `querySelector` / `querySelectorAll`

調査日: 2026-08-05

## ID参照

`app.js` のID参照は `getDomById()` に集約した。以下の28 IDは `REQUIRED_DOM_IDS` で起動時に存在数を検証し、0件または2件以上ならコンソールに警告する。

| ID | 主な用途 |
|---|---|
| `article-modal` | 記事モーダルの開閉、オーバーレイクリック |
| `modal-close-btn` | モーダルを閉じるボタン |
| `modal-thumb-wrap` | モーダルのサムネイル描画 |
| `modal-meta` | モーダルの記事メタ情報描画 |
| `modal-title` | モーダルの記事タイトル描画 |
| `modal-summary` | モーダルの記事要約描画 |
| `modal-read-btn` | 元記事リンクと計測イベント |
| `category-filter` | サイドバーのカテゴリ生成・選択イベント |
| `date-filter` | サイドバーの日付生成・選択イベント |
| `search-input` | キーワード検索イベント |
| `load-more-btn` | 追加表示イベントと残件数表示 |
| `sidebar` | モバイル開閉と選択後の自動クローズ |
| `articles-container` | 記事一覧・空状態・読込失敗の描画、スワイプ対象 |
| `load-more-wrapper` | 追加表示ボタン領域の表示切替 |
| `mobile-category-bar` | モバイルカテゴリ領域のDOM契約（スワイプ除外領域） |
| `mobile-cat-scroll` | モバイルカテゴリ生成・選択・スワイプ切替 |
| `mob-date-btn` | モバイル日付ドロップダウン開閉 |
| `mob-date-label` | 選択中の日付表示 |
| `mob-date-dropdown` | モバイル日付ドロップダウン本体 |
| `mob-date-list` | モバイル日付項目の生成・選択 |
| `sidebar-toggle` | モバイルサイドバー開閉ボタン |
| `tabbar` | ヘッダー内タブ切替のスコープ |
| `app-layout` | 既存記事領域全体のDOM契約 |
| `main` | 記事メイン領域のDOM契約 |
| `masthead-issue-no` | ISSUE番号表示 |
| `digest-stats` | 当日記事数・カテゴリ数表示 |
| `stats-bar` | 絞込後の記事数表示 |
| `article-list-start` | 検索・カテゴリ・日付絞込後のスクロール先 |

## querySelector / querySelectorAll参照

| セレクタ | スコープ | 用途・ガード |
|---|---|---|
| ``#${id}`` | `document` | `REQUIRED_DOM_IDS` 各IDの欠落・重複検証 |
| `#tabbar .tab-btn[data-tab]` | `document` | ヘッダー内かつ `data-tab` を持つタブだけを初期化・active切替。0件なら警告 |
| `#article-modal .modal-box` | `document` | モーダル必須子要素の欠落・重複検証 |
| `#category-filter .sidebar-item` | `document` | カテゴリ変更時のactive解除。0件でも安全なNodeList |
| `#date-filter .sidebar-item` | `document` | 日付変更時のactive解除。0件でも安全なNodeList |
| `.date-month-arrow` | 生成した `monthHeader` | 月アコーディオン矢印更新。取得後に存在確認 |
| `.mob-cat-btn` | `mobile-cat-scroll` | モバイルカテゴリのactive解除・スワイプ対象取得。親要素を先に存在確認 |
| `.modal-box` | `article-modal` | モバイルのモーダル内タップ処理。取得後に存在確認 |

旧セレクタ `.tab-btn` は廃止し、ランディングやフッターに同名クラスが追加されても `state.tab` に影響しないスコープへ限定した。

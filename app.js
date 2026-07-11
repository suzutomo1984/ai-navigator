/* =============================================
   AI Navigator - メインアプリケーション v2
   ============================================= */

const PAGE_SIZE = 50;

// =============================================
// NEW判定（最新配信バッチとの一致）
// =============================================
// 訪問履歴ではなく「最新の配信バッチ(latestBatchAt)で追加された記事」だけをNEWとする。
// 誰が・いつ見ても同じ表示。次の配信が走ると前回分のNEWは自動的に消える。

let latestBatchAt = null;

function isNewArticle(article) {
  if (!latestBatchAt || !article.addedAt) return false;
  return article.addedAt === latestBatchAt;
}

// =============================================
// データ検証（パース失敗などで壊れた記事を除外）
// =============================================
// urlが空 = ソース行のパースに失敗した不完全な記事。表示すると
// タイトル欠けやリンク切れの見た目になるため一覧から除外する。

function isValidArticle(article) {
  return !!article.url;
}

// =============================================
// 状態管理
// =============================================

const state = {
  tab: "latest",
  category: "all",
  date: "all",
  search: "",
  page: 1,
  view: "paper", // 紙面表示に固定（カード/リストのトグルは廃止）
};

let allArticles = [];
let allDates = [];
let allCategories = [];
let searchTimer = null;
// ピック件数はデータ更新時にのみ変化するため、loadData()で一度だけ集計して保持する
// （render()のたびに全件スキャンするのを避ける）
let mustCount = 0;
let checkCount = 0;

// =============================================
// データ読み込み
// =============================================

async function loadData() {
  const res = await fetch("articles.json");
  const data = await res.json();

  allArticles = (data.articles || []).filter(isValidArticle);
  allDates = data.dates || [];
  allCategories = data.categories || [];
  latestBatchAt = data.latestBatchAt || null; // 最新配信バッチ時刻（NEW判定の基準）

  // ピック件数を一度だけ集計（以降のrender()では再計算しない）
  mustCount = allArticles.filter(a => a.isPick && a.pickPriority === "must-read").length;
  checkCount = allArticles.filter(a => a.isPick && a.pickPriority !== "must-read").length;

  buildSidebarFilters();
  buildMobileCategoryBar();
  buildMobileDateDropdown();
  render();
}


// =============================================
// サイドバーフィルター構築
// =============================================

function buildSidebarFilters() {
  // カテゴリフィルター（縦リスト）
  const catList = document.getElementById("category-filter");
  catList.innerHTML = `<li class="sidebar-item active" data-cat="all">ALL</li>`;

  allCategories
    .filter(c => c.articleCount > 0 && c.id !== "official")
    .forEach(c => {
      const li = document.createElement("li");
      li.className = "sidebar-item";
      li.dataset.cat = c.id;
      li.textContent = `${c.emoji} ${c.label}`;
      catList.appendChild(li);
    });

  buildDateFilter();
}

// 現在のカテゴリ・タブ状態に合わせて日付フィルターを再構築
function buildDateFilter() {
  // 現在のタブ・カテゴリで存在する記事の日付セットを取得
  const activeDates = new Set(
    allArticles
      .filter(a => {
        if (state.tab === "picks" && !a.isPick) return false;
        if (state.tab === "official" && !a.isOfficial) return false;
        if (state.tab === "latest" && a.isOfficial) return false;
        if (state.category !== "all" && a.category !== state.category) return false;
        return true;
      })
      .map(a => a.date)
  );

  // 全日付リストからactiveDatesに含まれる日付のみ抽出（順序維持）
  const validDates = allDates.filter(d => d.status === "ok" && activeDates.has(d.date));

  // 選択中の日付が存在しなくなったらallにリセット
  if (state.date !== "all" && !activeDates.has(state.date)) {
    state.date = "all";
  }

  // 日付フィルター（月別アコーディオン）再構築
  const dateContainer = document.getElementById("date-filter");
  dateContainer.innerHTML = `<li class="sidebar-item${state.date === "all" ? " active" : ""}" data-date="all">All</li>`;

  // 月ごとにグループ化
  const monthMap = new Map();
  validDates.forEach(d => {
    const dt = new Date(d.date);
    const monthKey = `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}`;
    const monthLabel = `${dt.getFullYear()}年${dt.getMonth() + 1}月`;
    if (!monthMap.has(monthKey)) monthMap.set(monthKey, { label: monthLabel, dates: [] });
    monthMap.get(monthKey).dates.push(d);
  });

  const now = new Date();
  const currentMonthKey = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;

  monthMap.forEach((month, monthKey) => {
    const isCurrentMonth = monthKey === currentMonthKey;

    const monthHeader = document.createElement("li");
    monthHeader.className = "date-month-header";
    monthHeader.innerHTML = `<span>${month.label}</span><span class="date-month-arrow">${isCurrentMonth ? "▼" : "▶"}</span>`;

    const monthDates = document.createElement("ul");
    monthDates.className = "date-month-list" + (isCurrentMonth ? " open" : "");

    month.dates.forEach(d => {
      const li = document.createElement("li");
      li.className = "sidebar-item" + (state.date === d.date ? " active" : "");
      li.dataset.date = d.date;
      const dt = new Date(d.date);
      const mm = dt.getMonth() + 1;
      const dd = dt.getDate();
      li.textContent = `${mm}/${dd}`;
      monthDates.appendChild(li);
    });

    monthHeader.addEventListener("click", () => {
      const isOpen = monthDates.classList.toggle("open");
      monthHeader.querySelector(".date-month-arrow").textContent = isOpen ? "▼" : "▶";
    });

    dateContainer.appendChild(monthHeader);
    dateContainer.appendChild(monthDates);
  });

  // モバイル日付ドロップダウンも同期
  rebuildMobileDateList(validDates);
}

// =============================================
// モバイルカテゴリタブバー構築
// =============================================

// カテゴリごとのタブカラー
const CAT_COLORS = {
  "all":              "#ff335f",
  "sales-marketing":  "#3b82f6",
  "back-office":      "#8b5cf6",
  "productivity":     "#f59e0b",
  "strategy":         "#10b981",
  "info-mgmt":        "#6366f1",
  "ai-tech":          "#06b6d4",
  "side-business":    "#eab308",
  "official":         "#6b7280",
  "other":            "#6b7280",
};

function buildMobileCategoryBar() {
  const scroll = document.getElementById("mobile-cat-scroll");
  if (!scroll) return;
  scroll.innerHTML = "";

  const allBtn = document.createElement("button");
  allBtn.className = "mob-cat-btn active";
  allBtn.dataset.cat = "all";
  allBtn.textContent = "ALL";
  allBtn.style.background = CAT_COLORS["all"];
  scroll.appendChild(allBtn);

  allCategories
    .filter(c => c.articleCount > 0 && c.id !== "official")
    .forEach(c => {
      const btn = document.createElement("button");
      btn.className = "mob-cat-btn";
      btn.dataset.cat = c.id;
      btn.textContent = `${c.emoji} ${c.label}`;
      btn.style.background = CAT_COLORS[c.id] || "#64748b";
      scroll.appendChild(btn);
    });

  scroll.addEventListener("click", e => {
    const btn = e.target.closest(".mob-cat-btn");
    if (!btn) return;
    scroll.querySelectorAll(".mob-cat-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    state.category = btn.dataset.cat;
    state.page = 1;
    buildDateFilter();
    render(true);
  });
}

function buildMobileDateDropdown() {
  const btn = document.getElementById("mob-date-btn");
  const dropdown = document.getElementById("mob-date-dropdown");
  const list = document.getElementById("mob-date-list");
  if (!list || !btn || !dropdown) return;

  // 開閉イベント（初回のみ登録）
  btn.addEventListener("click", () => {
    dropdown.classList.toggle("open");
    btn.classList.toggle("active");
  });

  // 日付アイテム選択
  list.addEventListener("click", e => {
    const item = e.target.closest(".mob-date-item");
    if (!item) return;
    state.date = item.dataset.date;
    state.page = 1;
    const label = document.getElementById("mob-date-label");
    if (label) label.textContent = item.dataset.date === "all" ? "日付" : item.textContent;
    dropdown.classList.remove("open");
    btn.classList.remove("active");
    buildDateFilter();
    render(true);
  });

  // 初期リスト構築
  const validDates = allDates.filter(d => d.status === "ok" && d.articleCount > 0);
  rebuildMobileDateList(validDates);
}

// モバイル日付リストをvalidDatesで再構築（buildDateFilterから呼ばれる）
function rebuildMobileDateList(validDates) {
  const list = document.getElementById("mob-date-list");
  if (!list) return;

  list.innerHTML = "";

  const allItem = document.createElement("button");
  allItem.className = "mob-date-item" + (state.date === "all" ? " active" : "");
  allItem.dataset.date = "all";
  allItem.textContent = "すべて";
  list.appendChild(allItem);

  validDates.forEach(d => {
    const item = document.createElement("button");
    item.className = "mob-date-item" + (state.date === d.date ? " active" : "");
    item.dataset.date = d.date;
    const dt = new Date(d.date);
    item.textContent = `${dt.getMonth() + 1}/${dt.getDate()}`;
    list.appendChild(item);
  });

  // ラベル更新
  const label = document.getElementById("mob-date-label");
  if (label) {
    if (state.date === "all") {
      label.textContent = "日付";
    } else {
      const dt = new Date(state.date);
      label.textContent = `${dt.getMonth() + 1}/${dt.getDate()}`;
    }
  }
}

// =============================================
// フィルタリング
// =============================================

function filterArticles() {
  return allArticles.filter(a => {
    if (state.tab === "picks" && !a.isPick) return false;
    if (state.tab === "official" && !a.isOfficial) return false;
    if (state.tab === "latest" && a.isOfficial) return false;
    if (state.category !== "all" && a.category !== state.category) return false;
    if (state.date !== "all" && a.date !== state.date) return false;
    if (state.search) {
      const q = state.search.toLowerCase();
      const inTitle = a.title.toLowerCase().includes(q);
      const inSummary = a.summary.toLowerCase().includes(q);
      const inSource = a.source.toLowerCase().includes(q);
      if (!inTitle && !inSummary && !inSource) return false;
    }
    return true;
  });
}

// =============================================
// ソート
// =============================================

function sortArticles(articles) {
  if (state.tab === "ranking") {
    return [...articles].sort((a, b) => {
      if (a.rankingTier !== b.rankingTier) return a.rankingTier - b.rankingTier;
      return b.rankingScore - a.rankingScore;
    });
  }
  return [...articles].sort((a, b) => {
    if (a.date !== b.date) return b.date.localeCompare(a.date);
    const aNew = isNewArticle(a);
    const bNew = isNewArticle(b);
    if (aNew !== bNew) return aNew ? -1 : 1;
    if (a.isPick && !b.isPick) return -1;
    if (!a.isPick && b.isPick) return 1;
    if (a.pickPriority === "must-read" && b.pickPriority !== "must-read") return -1;
    if (a.pickPriority !== "must-read" && b.pickPriority === "must-read") return 1;
    return a.id.localeCompare(b.id);
  });
}

// =============================================
// 記事カード生成
// =============================================

function openModal(article) {
  const modal = document.getElementById("article-modal");
  const categoryLabel = allCategories.find(c => c.id === article.category);
  const catText = categoryLabel ? categoryLabel.label : article.category;

  // GA4: 記事の要約を開いた＝最も濃い関心シグナル。どの記事/カテゴリ/ソースが刺さったかを計測
  if (typeof gtag === "function") {
    gtag("event", "select_content", {
      content_type: "article",
      item_id: article.url || "",
      item_name: article.title || "",
      item_category: catText || article.category || "",
      item_brand: article.source || "",
    });
  }

  // サムネイル
  const thumbWrap = document.getElementById("modal-thumb-wrap");
  if (article.thumbnail) {
    thumbWrap.innerHTML = `<img src="${article.thumbnail}" alt="" onerror="onThumbError(this)">`;
    thumbWrap.style.display = "block";
  } else {
    thumbWrap.innerHTML = "";
    thumbWrap.style.display = "none";
  }

  // メタ情報
  const officialBadge = article.isOfficial ? `<span class="card-badge official-badge">📦 リリースノート</span>` : "";
  document.getElementById("modal-meta").innerHTML = `
    ${article.source ? `<span class="card-badge">${escHtml(article.source)}</span>` : ""}
    <span class="card-badge">${escHtml(catText)}</span>
    ${officialBadge}
    ${article.date ? `<span class="card-date">${article.date.slice(5).replace("-", "/")}</span>` : ""}
  `;

  document.getElementById("modal-title").textContent = article.title || "";
  document.getElementById("modal-summary").textContent = article.summary || "（要約なし）";
  const readBtn = document.getElementById("modal-read-btn");
  readBtn.href = article.url || "#";

  // GA4: 「読む」=元記事まで読みに行った深い関心シグナル。要約を開いた(select_content)の一段先。
  // onclickで上書き代入（openModalは記事ごとに呼ばれるためaddEventListenerだと多重登録になる）
  readBtn.onclick = () => {
    if (typeof gtag === "function") {
      gtag("event", "select_item", {
        content_type: "article_outbound",
        item_id: article.url || "",
        item_name: article.title || "",
        item_category: catText || article.category || "",
        item_brand: article.source || "",
      });
    }
  };

  modal.setAttribute("aria-hidden", "false");
  modal.classList.add("open");
  document.body.style.overflow = "hidden";
  document.documentElement.style.overflow = "hidden";

  // スマホのみ: 記事を読む以外のモーダル内タップで閉じる
  if (window.innerWidth <= 768) {
    const box = modal.querySelector(".modal-box");
    const readBtn = document.getElementById("modal-read-btn");
    const onTap = e => {
      if (!readBtn.contains(e.target)) {
        closeModal();
        box.removeEventListener("click", onTap);
      }
    };
    box.addEventListener("click", onTap);
  }
}

function closeModal() {
  const modal = document.getElementById("article-modal");
  modal.classList.remove("open");
  modal.setAttribute("aria-hidden", "true");
  document.body.style.overflow = "";
  document.documentElement.style.overflow = "";
}

function createCard(article, isRanking = false) {
  const card = document.createElement("div");
  card.className = "article-card";

  if (article.isPick) {
    card.classList.add(article.pickPriority === "must-read" ? "pick-must" : "pick-check");
  }
  if (isNewArticle(article)) {
    card.classList.add("is-new");
  }

  const newBadge = isNewArticle(article) ? `<span class="new-badge">NEW</span>` : "";
  const pickBadge = article.isPick
    ? `<span class="pick-badge">${article.pickPriority === "must-read" ? "🔴" : "🟡"}</span>`
    : "";

  const tierBadge = isRanking
    ? `<span class="tier-badge tier-${article.rankingTier}">${
        article.rankingTier === 1 ? "MUST" : article.rankingTier === 2 ? "CHECK" : "─"
      }</span>`
    : "";

  const rankScore = isRanking
    ? `<span class="rank-score">★${article.rankingScore}</span>`
    : "";

  const categoryLabel = allCategories.find(c => c.id === article.category);
  const catText = categoryLabel ? `${categoryLabel.label}` : article.category;

  const sourceBadge = article.source
    ? `<span class="card-badge">${escHtml(article.source)}</span>`
    : "";

  const catBadge = `<span class="card-badge">${escHtml(catText)}</span>`;
  const officialBadge = article.isOfficial ? `<span class="card-badge official-badge">📦 リリースノート</span>` : "";
  const dateBadge = article.date
    ? `<span class="card-date">${article.date.slice(5).replace("-", "/")}</span>`
    : "";

  const thumbHtml = article.thumbnail
    ? `<div class="card-thumb"><img src="${article.thumbnail}" alt="" loading="lazy" onerror="onThumbError(this)"></div>`
    : "";

  card.innerHTML = `
    ${thumbHtml}
    <div class="card-body">
      <div class="card-header">
        ${newBadge}${pickBadge}
        <div class="card-title">${escHtml(article.title)}</div>
        ${rankScore}
      </div>
      <div class="card-meta">
        ${sourceBadge}
        ${catBadge}
        ${officialBadge}
        ${tierBadge}
        ${dateBadge}
      </div>
      ${article.summary ? `<div class="card-summary">${escHtml(article.summary)}</div>` : ""}
    </div>
  `;

  card.addEventListener("click", () => openModal(article));

  return card;
}

// サムネ画像読み込み失敗時: 枠を消し、祖先のクリック要素に no-thumb を付けて本文をフル幅化
function onThumbError(img) {
  const wrap = img.parentElement;
  if (wrap) wrap.style.display = "none";
  const host = img.closest(".article-card, .paper-lead, .paper-chlead, .paper-cell");
  if (host) host.classList.add("no-thumb");
}

function escHtml(str) {
  return (str || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// =============================================
// 新聞マストヘッド更新（発行物メタファー）
// =============================================

function updateMasthead(todayStr) {
  // 号数: 最新記事日付 YYYY-MM-DD → MMDD（例: 2026-06-21 → 0621）
  const issueEl = document.getElementById("masthead-issue-no");
  if (issueEl) {
    const m = todayStr && /^\d{4}-(\d{2})-(\d{2})$/.exec(todayStr);
    issueEl.textContent = m ? `${m[1]}${m[2]}` : "----";
  }

  // ダイジェスト統計: 本日号「<本日件数> HEADLINES · <本日カテゴリ数> CATEGORIES」
  const statsEl = document.getElementById("digest-stats");
  if (statsEl) {
    const todayArticles = allArticles.filter(
      a => !a.isOfficial && a.date === todayStr
    );
    const headlineCount = todayArticles.length;
    const catCount = new Set(
      todayArticles.map(a => a.category).filter(Boolean)
    ).size;
    statsEl.textContent = `${headlineCount} HEADLINES · ${catCount} CATEGORIES`;
  }
}

// =============================================
// 罫線リスト描画（カテゴリ別番号付きセクション / OrangeBot風）
// =============================================

function renderDateAsList(dateStr, filtered, listEl) {
  // その日付の記事を全件取得（リストは情報密度重視で全件表示）
  const dayArticles = filtered.filter(a => a.date === dateStr);

  // カテゴリごとにグルーピング（allCategoriesの並び順を尊重）
  const orderedCats = allCategories.filter(
    c => c.id !== "official" && dayArticles.some(a => a.category === c.id)
  );
  // allCategoriesに無いカテゴリの記事は末尾にまとめる
  const knownCatIds = new Set(orderedCats.map(c => c.id));
  const hasOther = dayArticles.some(a => !knownCatIds.has(a.category));

  let secNo = 0;
  const buildSection = (catId, emoji, label) => {
    const items = dayArticles.filter(a =>
      catId === "__other__" ? !knownCatIds.has(a.category) : a.category === catId
    );
    if (items.length === 0) return;
    secNo += 1;
    const no = String(secNo).padStart(2, "0");

    const section = document.createElement("div");
    section.className = "list-section";

    const head = document.createElement("div");
    head.className = "list-section-head";
    head.innerHTML = `
      <span class="list-sec-no">${no}</span>
      <span class="list-sec-emoji">${emoji || ""}</span>
      <span class="list-sec-label">${escHtml(label)}</span>
      <span class="list-sec-count">${items.length}</span>
    `;
    section.appendChild(head);

    items.forEach(article => {
      const row = document.createElement("a");
      row.className = "list-row";
      row.href = article.url || "#";
      if (article.isPick) {
        row.classList.add(article.pickPriority === "must-read" ? "row-must" : "row-check");
      }
      const pick = article.isPick
        ? `<span class="row-pick">${article.pickPriority === "must-read" ? "🔴" : "🟡"}</span>`
        : "";
      const isNew = isNewArticle(article) ? `<span class="row-new">NEW</span>` : "";
      const src = article.source ? `<span class="row-source">${escHtml(article.source)}</span>` : "";
      row.innerHTML = `
        <span class="row-marker">▸</span>
        <span class="row-main">
          <span class="row-title">${isNew}${pick}${escHtml(article.title)}</span>
          ${src}
        </span>
      `;
      row.addEventListener("click", e => {
        e.preventDefault();
        openModal(article);
      });
      section.appendChild(row);
    });

    listEl.appendChild(section);
  };

  orderedCats.forEach(c => buildSection(c.id, c.emoji, c.label));
  if (hasOther) buildSection("__other__", "📦", "その他");
}

// =============================================
// 紙面描画（大1＋小N マルチカラム / 本物の新聞）
// =============================================

function renderDateAsPaper(dateStr, filtered, paperEl) {
  const dayArticles = filtered.filter(a => a.date === dateStr);
  if (dayArticles.length === 0) return;

  // トップ記事を選定: NEW最優先 > PICK最上位(must-read) > PICK(check) > 先頭
  // 夕方配信の新記事はMD末尾に追記されるため配列後方に来る。NEWを最優先にして
  // 「最新の配信で追加された記事」が必ず面トップに立つようにする（更新感を出す）。
  const score = a => {
    const newBonus = isNewArticle(a) ? 100 : 0;
    const pickBonus = a.isPick ? (a.pickPriority === "must-read" ? 2 : 1) : 0;
    return newBonus + pickBonus;
  };
  let leadIdx = 0;
  let best = -1;
  dayArticles.forEach((a, i) => {
    const s = score(a);
    if (s > best) { best = s; leadIdx = i; }
  });
  const lead = dayArticles[leadIdx];
  const rest = dayArticles.filter((_, i) => i !== leadIdx);

  const catLabel = a => {
    const c = allCategories.find(x => x.id === a.category);
    return c ? c.label : (a.category || "");
  };
  const pickMark = a => a.isPick
    ? `<span class="paper-pick">${a.pickPriority === "must-read" ? "🔴" : "🟡"}</span>` : "";
  const newMark = a => isNewArticle(a) ? `<span class="row-new">NEW</span>` : "";

  // セル生成ヘルパー（tier: "mid"=サムネ付き中見出し / "small"=テキストのみ）
  const makeCell = (article, tier, extraClass) => {
    const cell = document.createElement("a");
    cell.className = "paper-cell paper-cell-" + tier + (extraClass ? " " + extraClass : "");
    cell.href = article.url || "#";
    if (article.isPick) cell.classList.add(article.pickPriority === "must-read" ? "row-must" : "row-check");
    const thumb = ((tier === "mid" || tier === "small") && article.thumbnail)
      ? `<div class="paper-cell-thumb"><img src="${article.thumbnail}" alt="" loading="lazy" onerror="onThumbError(this)"></div>`
      : "";
    cell.innerHTML = `
      ${thumb}
      <div class="paper-cell-body">
        <div class="paper-cell-cat">${escHtml(catLabel(article))}</div>
        <h4 class="paper-cell-title">${newMark(article)}${pickMark(article)}${escHtml(article.title)}</h4>
        ${article.source ? `<span class="paper-source">${escHtml(article.source)}</span>` : ""}
      </div>
    `;
    cell.addEventListener("click", e => { e.preventDefault(); openModal(article); });
    return cell;
  };

  // --- 3階層に振り分け: 大1 / 中(サイド) / 小(下段) ---
  const SIDE_COUNT = 3;   // 大記事の右に並べる中記事
  const MID_BELOW = 3;    // 下段の頭に置く中記事（サムネ付き）
  const sideArticles = rest.slice(0, SIDE_COUNT);
  const midBelowArticles = rest.slice(SIDE_COUNT, SIDE_COUNT + MID_BELOW);
  const smallArticles = rest.slice(SIDE_COUNT + MID_BELOW);

  const topBlock = document.createElement("div");
  topBlock.className = "paper-top";

  // 大セル
  const leadEl = document.createElement("a");
  leadEl.className = "paper-lead";
  leadEl.href = lead.url || "#";
  if (lead.isPick) leadEl.classList.add(lead.pickPriority === "must-read" ? "row-must" : "row-check");
  const leadThumb = lead.thumbnail
    ? `<div class="paper-lead-thumb"><img src="${lead.thumbnail}" alt="" loading="lazy" onerror="onThumbError(this)"></div>`
    : "";
  leadEl.innerHTML = `
    ${leadThumb}
    <div class="paper-lead-body">
      <div class="paper-kicker">${newMark(lead)}${pickMark(lead)}<span class="paper-kicker-cat">${escHtml(catLabel(lead))}</span></div>
      <h3 class="paper-lead-title">${escHtml(lead.title)}</h3>
      ${lead.summary ? `<p class="paper-lead-summary">${escHtml(lead.summary)}</p>` : ""}
      ${lead.source ? `<span class="paper-source">${escHtml(lead.source)}</span>` : ""}
    </div>
  `;
  leadEl.addEventListener("click", e => { e.preventDefault(); openModal(lead); });
  topBlock.appendChild(leadEl);

  // サイド中セル（大記事の右に回り込む / サムネ付き中見出し）
  const sideWrap = document.createElement("div");
  sideWrap.className = "paper-side";
  sideArticles.forEach(a => sideWrap.appendChild(makeCell(a, "mid", "paper-cell-onside")));
  topBlock.appendChild(sideWrap);

  paperEl.appendChild(topBlock);

  // --- 中段: サムネ付き中記事の横並び（視覚的フック） ---
  if (midBelowArticles.length > 0) {
    const midWrap = document.createElement("div");
    midWrap.className = "paper-midrow";
    midBelowArticles.forEach(a => midWrap.appendChild(makeCell(a, "mid")));
    paperEl.appendChild(midWrap);
  }

  // --- 下段: カテゴリ別の章立て（01 営業・マーケ … 長いリストを章で割る） ---
  // 全カテゴリの章見出しを必ず出す（その日の記事が上段に吸われた／0件でも見出しは出す）
  {
    // カテゴリごとにグルーピング（allCategoriesの並び順を尊重）
    const knownIds = new Set(allCategories.map(c => c.id));
    // ALL表示時は official/other を除く全カテゴリの章見出しを必ず出す（0件は「配信なし」）。
    // 特定カテゴリで絞り込み中は、そのカテゴリの章だけ出す（他カテゴリの「配信なし」章は出さない）。
    const filteringCat = state.category !== "all";
    const orderedCats = allCategories.filter(c =>
      c.id !== "official" && c.id !== "other" &&
      (!filteringCat || c.id === state.category)
    );
    // 「その他」は、ALL表示 or その他で絞り込み中、かつ未知カテゴリ記事が実在する日だけ出す
    const hasOther =
      (!filteringCat || state.category === "other") &&
      dayArticles.some(a => !knownIds.has(a.category));

    // 章トップ記事（面トップ / 中サイズの大記事: サムネ中＋見出し中＋リード2行）
    const makeChapterLead = article => {
      const el = document.createElement("a");
      el.className = "paper-chlead";
      el.href = article.url || "#";
      if (article.isPick) el.classList.add(article.pickPriority === "must-read" ? "row-must" : "row-check");
      const thumb = article.thumbnail
        ? `<div class="paper-chlead-thumb"><img src="${article.thumbnail}" alt="" loading="lazy" onerror="onThumbError(this)"></div>`
        : "";
      el.innerHTML = `
        ${thumb}
        <div class="paper-chlead-body">
          <div class="paper-cell-cat">${escHtml(catLabel(article))}</div>
          <h3 class="paper-chlead-title">${newMark(article)}${pickMark(article)}${escHtml(article.title)}</h3>
          ${article.summary ? `<p class="paper-chlead-summary">${escHtml(article.summary)}</p>` : ""}
          ${article.source ? `<span class="paper-source">${escHtml(article.source)}</span>` : ""}
        </div>
      `;
      el.addEventListener("click", e => { e.preventDefault(); openModal(article); });
      return el;
    };

    let chapterNo = 0;
    const CH_SIDE = 4;        // 章トップの右に並べる中記事数
    const buildChapter = (catId, emoji, label) => {
      const match = a => catId === "__other__" ? !knownIds.has(a.category) : a.category === catId;
      const items = smallArticles.filter(match);
      // 下段に記事が無くても見出しは必ず出す。
      // ただし上段（大・中記事）に同カテゴリが居るなら「配信なし」は誤りなので状態を出し分ける。
      const inTopOnly = items.length === 0 && dayArticles.some(match);
      chapterNo += 1;
      const no = String(chapterNo).padStart(2, "0");

      const head = document.createElement("div");
      head.className = "paper-chapter-head" + (items.length === 0 ? " paper-chapter-empty" : "");
      const countHtml = items.length > 0
        ? `<span class="paper-chapter-count">${items.length}</span>`
        : `<span class="paper-chapter-note">${inTopOnly ? "注目記事に掲載" : "本日の配信なし"}</span>`;
      head.innerHTML = `
        <span class="paper-chapter-no">${no}</span>
        <span class="paper-chapter-emoji">${emoji || ""}</span>
        <span class="paper-chapter-label">${escHtml(label)}</span>
        ${countHtml}
      `;
      paperEl.appendChild(head);
      // 記事が無い章は見出しのみで終了
      if (items.length === 0) return;

      // どの章も必ず大記事（面トップ）を出す。記事数に応じてレイアウトを可変にし、
      // 少数でも右側に空白が出ないようにする（1件=横幅ワイド / 2件以上=大記事＋右サイド）。
      const chLead = items[0];
      const chSide = items.slice(1, 1 + CH_SIDE);
      const chSmall = items.slice(1 + CH_SIDE);

      // 章トップブロック: 面トップ（中）＋右に中記事
      const top = document.createElement("div");
      // サイド記事が無い（=1件のみ）章は大記事を全幅に広げて空白を防ぐ
      top.className = "paper-chapter-top" + (chSide.length === 0 ? " paper-chapter-top-single" : "");
      top.appendChild(makeChapterLead(chLead));
      if (chSide.length > 0) {
        const side = document.createElement("div");
        side.className = "paper-side";
        chSide.forEach(a => side.appendChild(makeCell(a, "mid", "paper-cell-onside")));
        top.appendChild(side);
      }
      paperEl.appendChild(top);

      // 章の残り: 小記事グリッド
      if (chSmall.length > 0) {
        const grid = document.createElement("div");
        grid.className = "paper-rest";
        chSmall.forEach(a => grid.appendChild(makeCell(a, "small")));
        paperEl.appendChild(grid);
      }
    };

    orderedCats.forEach(c => buildChapter(c.id, c.emoji, c.label));
    if (hasOther) buildChapter("__other__", "📦", "その他");
  }
}

// =============================================
// レンダリング
// =============================================

function render(resetScroll = false) {
  // 日付・カテゴリ・タブ・検索の切り替え時はページ最上部に戻す
  // （「もっと見る」のページ送りは現在位置を維持するため resetScroll を渡さない）
  if (resetScroll) window.scrollTo(0, 0);

  const filtered = filterArticles();
  const sorted = sortArticles(filtered);
  const visible = sorted.slice(0, state.page * PAGE_SIZE);
  const hasMore = visible.length < sorted.length;

  // 統計バー
  const todayStr = allDates.length > 0 ? allDates[0].date : null;
  const todayCount = todayStr ? filtered.filter(a => a.date === todayStr).length : 0;
  // mustCount / checkCount は loadData() で集計済み（グローバル変数を参照）
  const statsEl = document.getElementById("stats-bar");
  statsEl.innerHTML = `
    <span class="stats-item">📰 ${filtered.length}件表示中</span>
    <span class="stats-sep">|</span>
    <span class="stats-item">本日 <strong>${todayCount}件</strong></span>
    ${mustCount > 0 ? `<span class="stats-sep">|</span><span class="stats-item">🔴マスト <strong>${mustCount}</strong></span>` : ""}
    ${checkCount > 0 ? `<span class="stats-sep">|</span><span class="stats-item">🟡チェック <strong>${checkCount}</strong></span>` : ""}
  `;

  updateMasthead(todayStr);

  const container = document.getElementById("articles-container");
  container.innerHTML = "";

  if (visible.length === 0) {
    container.innerHTML = `
      <div id="empty-state">
        <div class="empty-icon">🔍</div>
        <div>記事が見つかりませんでした</div>
      </div>`;
    document.getElementById("load-more-wrapper").style.display = "none";
    return;
  }

  const isRanking = state.tab === "ranking";

  if (isRanking) {
    // RANKINGは日付グループなしのグリッド
    const group = document.createElement("div");
    group.className = "date-group";
    const grid = document.createElement("div");
    grid.className = "article-cards-grid";
    visible.forEach(article => grid.appendChild(createCard(article, true)));
    group.appendChild(grid);
    container.appendChild(group);
  } else {
    // LATEST/PICKS: 日付グルーピング
    let currentDate = null;
    let dateCards = null;

    visible.forEach(article => {
      if (article.date !== currentDate) {
        currentDate = article.date;
        const countForDate = filtered.filter(a => a.date === currentDate).length;
        const dt = new Date(currentDate);
        const days = ["SUN","MON","TUE","WED","THU","FRI","SAT"];
        const dayLabel = days[dt.getDay()];
        const mm = dt.getMonth() + 1;
        const dd = dt.getDate();

        const dateGroup = document.createElement("div");
        dateGroup.className = "date-group";

        const header = document.createElement("div");
        header.className = "date-header";
        header.innerHTML = `
          <span class="date-label">${mm}/${dd} (${dayLabel})</span>
          <span class="date-count">${countForDate}</span>
        `;
        dateGroup.appendChild(header);

        // dailySummaryをウィジェットと同じデザインで表示
        const dateInfo = allDates.find(d => d.date === currentDate);
        if (dateInfo && dateInfo.dailySummary && dateInfo.dailySummary.trim()) {
          const summary = document.createElement("div");
          summary.className = "date-daily-summary";
          summary.innerHTML = `
            <div class="summary-header">
              <span class="summary-date">📅 ${mm}/${dd} のAIビジネスニュース</span>
              <span class="summary-count">${dateInfo.articleCount || 0}件</span>
            </div>
            <div class="summary-text">${escHtml(dateInfo.dailySummary)}</div>
          `;
          dateGroup.appendChild(summary);
        }

        if (state.view === "list") {
          // 罫線リスト: カテゴリ別番号付きセクション（OrangeBot風）
          dateCards = document.createElement("div");
          dateCards.className = "article-list";
          dateGroup.appendChild(dateCards);
          renderDateAsList(currentDate, filtered, dateCards);
        } else if (state.view === "paper") {
          // 紙面: 大1＋小Nのマルチカラムグリッド（本物の新聞）
          dateCards = document.createElement("div");
          dateCards.className = "article-paper";
          dateGroup.appendChild(dateCards);
          renderDateAsPaper(currentDate, filtered, dateCards);
        } else {
          dateCards = document.createElement("div");
          dateCards.className = "article-cards-grid";
          dateGroup.appendChild(dateCards);
        }

        container.appendChild(dateGroup);
      }
      // カード表示時のみ1件ずつ追加（リスト・紙面はセクション一括描画済み）
      if (state.view === "cards") {
        dateCards.appendChild(createCard(article, false));
      }
    });
  }

  // もっと見るボタン
  const loadMoreWrapper = document.getElementById("load-more-wrapper");
  if (hasMore) {
    loadMoreWrapper.style.display = "block";
    document.getElementById("load-more-btn").textContent =
      `もっと見る (残り${sorted.length - visible.length}件)`;
  } else {
    loadMoreWrapper.style.display = "none";
  }
}

// =============================================
// イベントハンドラー
// =============================================

function setupEvents() {
  // モーダル閉じる
  document.getElementById("modal-close-btn").addEventListener("click", closeModal);
  document.getElementById("article-modal").addEventListener("click", e => {
    if (e.target === e.currentTarget) closeModal();
  });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") closeModal();
  });

  // タブ切替
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      state.tab = btn.dataset.tab;
      state.page = 1;
      buildDateFilter();
      render(true);
    });
  });

  // カテゴリフィルター（サイドバー縦リスト）
  document.getElementById("category-filter").addEventListener("click", e => {
    const item = e.target.closest(".sidebar-item");
    if (!item) return;
    document.querySelectorAll("#category-filter .sidebar-item").forEach(i => i.classList.remove("active"));
    item.classList.add("active");
    state.category = item.dataset.cat;
    state.page = 1;
    buildDateFilter();
    render(true);
  });

  // 日付フィルター（サイドバー縦リスト）
  document.getElementById("date-filter").addEventListener("click", e => {
    const item = e.target.closest(".sidebar-item");
    if (!item) return;
    document.querySelectorAll("#date-filter .sidebar-item").forEach(i => i.classList.remove("active"));
    item.classList.add("active");
    state.date = item.dataset.date;
    state.page = 1;
    render(true);
  });

  // テキスト検索（300ms debounce）
  document.getElementById("search-input").addEventListener("input", e => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.search = e.target.value.trim();
      state.page = 1;
      render(true);
    }, 300);
  });

  // もっと見る
  document.getElementById("load-more-btn").addEventListener("click", () => {
    state.page++;
    render();
  });

  // モバイルサイドバートグル
  const sidebarToggle = document.getElementById("sidebar-toggle");
  const sidebar = document.getElementById("sidebar");
  if (sidebarToggle) {
    sidebarToggle.addEventListener("click", () => {
      sidebar.classList.toggle("open");
    });
  }

  // サイドバーアイテムクリック後（モバイル）: 自動的にサイドバーを閉じる
  sidebar.addEventListener("click", e => {
    if (e.target.closest(".sidebar-item") && window.innerWidth <= 768) {
      sidebar.classList.remove("open");
    }
  });
}

// =============================================
// スワイプでカテゴリ切替（モバイル・ページめくりアニメーション）
// =============================================

function setupSwipe() {
  if (window.innerWidth > 768) return;

  const container = document.getElementById("articles-container");
  const main = document.getElementById("main");
  let startX = 0, startY = 0, currentX = 0;
  let isSwiping = false;
  let isAnimating = false;
  let swipeDisabled = false; // 上部カテゴリバー等、独自に横スクロールする領域では切替スワイプを止める

  function getNextIdx(dx) {
    const scroll = document.getElementById("mobile-cat-scroll");
    if (!scroll) return null;
    const btns = [...scroll.querySelectorAll(".mob-cat-btn")];
    const activeIdx = btns.findIndex(b => b.classList.contains("active"));
    const nextIdx = dx < 0
      ? Math.min(activeIdx + 1, btns.length - 1)
      : Math.max(activeIdx - 1, 0);
    return nextIdx === activeIdx ? null : { btns, activeIdx, nextIdx };
  }

  document.addEventListener("touchstart", e => {
    if (isAnimating) return;
    // 上部カテゴリバー・日付ドロップダウン上で始まったタッチは独自スクロールに任せ、
    // カテゴリ切替スワイプとして拾わない（誤検知で動作が悪くなるのを防ぐ）
    swipeDisabled = !!(e.target.closest && e.target.closest("#mobile-category-bar, #mob-date-dropdown"));
    startX = e.touches[0].clientX;
    startY = e.touches[0].clientY;
    currentX = 0;
    isSwiping = false;
  }, { passive: true });

  document.addEventListener("touchmove", e => {
    if (isAnimating || swipeDisabled) return;
    const dx = e.touches[0].clientX - startX;
    const dy = e.touches[0].clientY - startY;

    // 縦スクロールが先に動いたら無視
    if (!isSwiping && Math.abs(dy) > Math.abs(dx)) return;

    if (Math.abs(dx) > 8) {
      isSwiping = true;
      currentX = dx;
      // 指に追従（抵抗感を持たせる）
      const resist = Math.min(Math.abs(dx), 80) / Math.abs(dx);
      container.style.transform = `translateX(${dx * resist * 0.4}px)`;
      container.style.transition = "none";
      container.style.opacity = `${1 - Math.min(Math.abs(dx) / 300, 0.3)}`;
    }
  }, { passive: true });

  document.addEventListener("touchend", e => {
    if (!isSwiping || isAnimating || swipeDisabled) {
      container.style.transform = "";
      container.style.transition = "";
      container.style.opacity = "";
      isSwiping = false;
      return;
    }

    const dx = e.changedTouches[0].clientX - startX;
    isSwiping = false;

    if (Math.abs(dx) < 50) {
      // キャンセル：元に戻す
      container.style.transition = "transform 0.2s ease, opacity 0.2s ease";
      container.style.transform = "translateX(0)";
      container.style.opacity = "1";
      return;
    }

    const result = getNextIdx(dx);
    if (!result) {
      container.style.transition = "transform 0.2s ease, opacity 0.2s ease";
      container.style.transform = "translateX(0)";
      container.style.opacity = "1";
      return;
    }

    const { btns, nextIdx } = result;
    const dir = dx < 0 ? -1 : 1;
    isAnimating = true;

    // 現在ページをスワイプ方向にスライドアウト
    container.style.transition = "transform 0.22s ease-in, opacity 0.22s ease-in";
    container.style.transform = `translateX(${dir * 100}%)`;
    container.style.opacity = "0";

    setTimeout(() => {
      // カテゴリ切替
      btns.forEach(b => b.classList.remove("active"));
      btns[nextIdx].classList.add("active");
      btns[nextIdx].scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
      state.category = btns[nextIdx].dataset.cat;
      state.page = 1;
      buildDateFilter();
      render(true);

      // 反対側から新ページをスライドイン
      container.style.transition = "none";
      container.style.transform = `translateX(${dir * -100}%)`;
      container.style.opacity = "0";

      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          container.style.transition = "transform 0.25s ease-out, opacity 0.25s ease-out";
          container.style.transform = "translateX(0)";
          container.style.opacity = "1";

          setTimeout(() => {
            container.style.transform = "";
            container.style.transition = "";
            container.style.opacity = "";
            isAnimating = false;
          }, 260);
        });
      });
    }, 230);
  }, { passive: true });
}

// =============================================
// 初期化
// =============================================

document.addEventListener("DOMContentLoaded", () => {
  setupEvents();
  setupSwipe();
  loadData().catch(err => {
    document.getElementById("articles-container").innerHTML = `
      <div id="empty-state">
        <div class="empty-icon">⚠️</div>
        <div>データの読み込みに失敗しました</div>
        <div style="font-size:12px;margin-top:8px;color:#484f58">${err.message}</div>
      </div>`;
  });
});

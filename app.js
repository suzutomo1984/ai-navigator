/* =============================================
   AI NEWS HUB - メインアプリケーション
   ============================================= */

const PAGE_SIZE = 50; // 初期表示件数

// =============================================
// 状態管理
// =============================================

const state = {
  tab: "latest",       // "latest" | "picks" | "ranking"
  category: "all",
  date: "all",
  search: "",
  page: 1,             // 表示ページ数（1 = 最初のPAGE_SIZE件）
};

let allArticles = [];
let allDates = [];
let allCategories = [];
let searchTimer = null;

// =============================================
// データ読み込み
// =============================================

async function loadData() {
  const res = await fetch("articles.json");
  const data = await res.json();

  allArticles = data.articles || [];
  allDates = data.dates || [];
  allCategories = data.categories || [];

  buildFilterBars();
  render();
}

// =============================================
// フィルターバー構築
// =============================================

function buildFilterBars() {
  // カテゴリフィルター
  const catBar = document.getElementById("category-filter");
  catBar.innerHTML = `<button class="filter-btn active" data-cat="all">ALL</button>`;
  allCategories
    .filter(c => c.articleCount > 0)
    .forEach(c => {
      const btn = document.createElement("button");
      btn.className = "filter-btn";
      btn.dataset.cat = c.id;
      btn.textContent = `${c.emoji} ${c.label}`;
      catBar.appendChild(btn);
    });

  // 日付フィルター（最新30日分）
  const dateBar = document.getElementById("date-filter");
  dateBar.innerHTML = `<button class="filter-btn active" data-date="all">All</button>`;
  allDates
    .filter(d => d.status === "ok" && d.articleCount > 0)
    .slice(0, 30)
    .forEach(d => {
      const btn = document.createElement("button");
      btn.className = "filter-btn";
      btn.dataset.date = d.date;
      const dt = new Date(d.date);
      const mm = dt.getMonth() + 1;
      const dd = dt.getDate();
      btn.textContent = `${mm}/${dd}`;
      dateBar.appendChild(btn);
    });
}

// =============================================
// フィルタリング
// =============================================

function filterArticles() {
  return allArticles.filter(a => {
    // タブ
    if (state.tab === "picks" && !a.isPick) return false;

    // カテゴリ
    if (state.category !== "all" && a.category !== state.category) return false;

    // 日付
    if (state.date !== "all" && a.date !== state.date) return false;

    // 検索
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
    // tier昇順 → score降順
    return [...articles].sort((a, b) => {
      if (a.rankingTier !== b.rankingTier) return a.rankingTier - b.rankingTier;
      return b.rankingScore - a.rankingScore;
    });
  }

  // LATEST / PICKS: 日付降順 → id順
  return [...articles].sort((a, b) => {
    if (a.date !== b.date) return b.date.localeCompare(a.date);
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

function createCard(article, isRanking = false) {
  const a = document.createElement("a");
  a.href = article.url || "#";
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  a.className = "article-card";

  if (article.isPick) {
    a.classList.add(article.pickPriority === "must-read" ? "pick-must" : "pick-check");
  }

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
  const catText = categoryLabel
    ? `${categoryLabel.emoji} ${categoryLabel.label}`
    : article.category;

  a.innerHTML = `
    <div class="card-header">
      ${pickBadge}
      <div class="card-title">${escHtml(article.title)}</div>
      ${rankScore}
    </div>
    <div class="card-meta">
      ${article.source ? `<span class="card-source">${escHtml(article.source)}</span>` : ""}
      <span class="card-category">${escHtml(catText)}</span>
      ${tierBadge}
    </div>
    ${article.summary ? `<div class="card-summary">${escHtml(article.summary)}</div>` : ""}
  `;

  return a;
}

function escHtml(str) {
  return (str || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// =============================================
// レンダリング
// =============================================

function render() {
  const filtered = filterArticles();
  const sorted = sortArticles(filtered);
  const visible = sorted.slice(0, state.page * PAGE_SIZE);
  const hasMore = visible.length < sorted.length;

  // 統計バー
  document.getElementById("stats-bar").textContent =
    `${filtered.length}件表示中 (全${allArticles.length}件)`;

  const main = document.getElementById("articles-container");
  main.innerHTML = "";

  if (visible.length === 0) {
    main.innerHTML = `
      <div id="empty-state">
        <div class="empty-icon">🔍</div>
        <div>記事が見つかりませんでした</div>
      </div>`;
    document.getElementById("load-more-wrapper").style.display = "none";
    return;
  }

  const isRanking = state.tab === "ranking";

  if (isRanking) {
    // RANKINGはフラットリスト
    visible.forEach(article => {
      main.appendChild(createCard(article, true));
    });
  } else {
    // LATEST/PICKSは日付グルーピング
    let currentDate = null;
    let dateGroup = null;
    let dateCards = null;

    visible.forEach(article => {
      if (article.date !== currentDate) {
        currentDate = article.date;
        const countForDate = filtered.filter(a => a.date === currentDate).length;
        const dt = new Date(currentDate);
        const days = ["SUN","MON","TUE","WED","THU","FRI","SAT"];
        const dayLabel = days[dt.getDay()];

        dateGroup = document.createElement("div");
        dateGroup.className = "date-group";

        const header = document.createElement("div");
        header.className = "date-header";
        const mm = dt.getMonth() + 1;
        const dd = dt.getDate();
        header.innerHTML = `
          <span class="date-label">${mm}/${dd} (${dayLabel})</span>
          <span class="date-count">${countForDate}</span>
        `;
        dateGroup.appendChild(header);

        dateCards = document.createElement("div");
        dateCards.className = "article-cards-grid";
        dateGroup.appendChild(dateCards);

        main.appendChild(dateGroup);
      }
      dateCards.appendChild(createCard(article, false));
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
  // タブ切替
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      state.tab = btn.dataset.tab;
      state.page = 1;
      render();
    });
  });

  // カテゴリフィルター
  document.getElementById("category-filter").addEventListener("click", e => {
    const btn = e.target.closest(".filter-btn");
    if (!btn) return;
    document.querySelectorAll("#category-filter .filter-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    state.category = btn.dataset.cat;
    state.page = 1;
    render();
  });

  // 日付フィルター
  document.getElementById("date-filter").addEventListener("click", e => {
    const btn = e.target.closest(".filter-btn");
    if (!btn) return;
    document.querySelectorAll("#date-filter .filter-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    state.date = btn.dataset.date;
    state.page = 1;
    render();
  });

  // テキスト検索（300ms debounce）
  document.getElementById("search-input").addEventListener("input", e => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.search = e.target.value.trim();
      state.page = 1;
      render();
    }, 300);
  });

  // もっと見る
  document.getElementById("load-more-btn").addEventListener("click", () => {
    state.page++;
    render();
    // スムーズスクロールしない（位置キープ）
  });
}

// =============================================
// 初期化
// =============================================

document.addEventListener("DOMContentLoaded", () => {
  setupEvents();
  loadData().catch(err => {
    document.getElementById("articles-container").innerHTML = `
      <div id="empty-state">
        <div class="empty-icon">⚠️</div>
        <div>データの読み込みに失敗しました</div>
        <div style="font-size:12px;margin-top:8px;color:#64748b">${err.message}</div>
      </div>`;
  });
});

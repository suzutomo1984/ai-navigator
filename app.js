/* =============================================
   AI Navigator - メインアプリケーション v2
   ============================================= */

const PAGE_SIZE = 50;

// =============================================
// 状態管理
// =============================================

const state = {
  tab: "latest",
  category: "all",
  date: "all",
  search: "",
  page: 1,
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

  buildSidebarFilters();
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

  // 日付フィルター（縦リスト、最新30日）
  const dateList = document.getElementById("date-filter");
  dateList.innerHTML = `<li class="sidebar-item active" data-date="all">All</li>`;
  allDates
    .filter(d => d.status === "ok" && d.articleCount > 0)
    .slice(0, 30)
    .forEach(d => {
      const li = document.createElement("li");
      li.className = "sidebar-item";
      li.dataset.date = d.date;
      const dt = new Date(d.date);
      const mm = dt.getMonth() + 1;
      const dd = dt.getDate();
      li.textContent = `${mm}/${dd}`;
      dateList.appendChild(li);
    });
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
  const catText = categoryLabel ? `${categoryLabel.label}` : article.category;

  // ソースバッジ（ドメイン短縮表示）
  const sourceBadge = article.source
    ? `<span class="card-badge">${escHtml(article.source)}</span>`
    : "";

  // カテゴリバッジ
  const catBadge = `<span class="card-badge">${escHtml(catText)}</span>`;

  // 公式バッジ
  const officialBadge = article.isOfficial ? `<span class="card-badge official-badge">📢 公式</span>` : "";

  const thumbHtml = article.thumbnail
    ? `<div class="card-thumb"><img src="${article.thumbnail}" alt="" loading="lazy" onerror="this.parentElement.style.display='none'"></div>`
    : "";

  a.innerHTML = `
    ${thumbHtml}
    <div class="card-body">
      <div class="card-header">
        ${pickBadge}
        <div class="card-title">${escHtml(article.title)}</div>
        ${rankScore}
      </div>
      <div class="card-meta">
        ${sourceBadge}
        ${catBadge}
        ${officialBadge}
        ${tierBadge}
      </div>
      ${article.summary ? `<div class="card-summary">${escHtml(article.summary)}</div>` : ""}
    </div>
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

        // dailySummary表示
        const dateInfo = allDates.find(d => d.date === currentDate);
        if (dateInfo && dateInfo.dailySummary) {
          const summary = document.createElement("div");
          summary.className = "daily-summary";
          summary.innerHTML = `<span class="daily-summary-icon">💡</span><span class="daily-summary-text">${escHtml(dateInfo.dailySummary)}</span>`;
          dateGroup.appendChild(summary);
        }

        dateCards = document.createElement("div");
        dateCards.className = "article-cards-grid";
        dateGroup.appendChild(dateCards);

        container.appendChild(dateGroup);
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

  // カテゴリフィルター（サイドバー縦リスト）
  document.getElementById("category-filter").addEventListener("click", e => {
    const item = e.target.closest(".sidebar-item");
    if (!item) return;
    document.querySelectorAll("#category-filter .sidebar-item").forEach(i => i.classList.remove("active"));
    item.classList.add("active");
    state.category = item.dataset.cat;
    state.page = 1;
    render();
  });

  // 日付フィルター（サイドバー縦リスト）
  document.getElementById("date-filter").addEventListener("click", e => {
    const item = e.target.closest(".sidebar-item");
    if (!item) return;
    document.querySelectorAll("#date-filter .sidebar-item").forEach(i => i.classList.remove("active"));
    item.classList.add("active");
    state.date = item.dataset.date;
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
// 初期化
// =============================================

document.addEventListener("DOMContentLoaded", () => {
  setupEvents();
  loadData().catch(err => {
    document.getElementById("articles-container").innerHTML = `
      <div id="empty-state">
        <div class="empty-icon">⚠️</div>
        <div>データの読み込みに失敗しました</div>
        <div style="font-size:12px;margin-top:8px;color:#484f58">${err.message}</div>
      </div>`;
  });
});

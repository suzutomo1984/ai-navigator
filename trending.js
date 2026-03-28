/* =============================================
   AI Navigator - GitHub Trendingページ
   ============================================= */

const PAGE_SIZE = 50;

const state = {
  date: "all",
  search: "",
  sort: "stars_desc",
  page: 1,
};

let allTrending = [];
let allDates = [];
let searchTimer = null;

async function loadData() {
  const res = await fetch("articles.json");
  const data = await res.json();

  allTrending = data.trending || [];
  allDates = [...new Set(allTrending.map(r => r.date))].sort((a, b) => b.localeCompare(a));

  buildSidebarFilters();
  buildMobileCategoryBar();
  buildMobileDateDropdown();
  render();
}

function buildSidebarFilters() {
  // ソートUI
  const sortContainer = document.getElementById("sort-filter");
  if (sortContainer) {
    const sorts = [
      { key: "stars_desc", label: "⭐ Stars 多い順" },
      { key: "stars_asc",  label: "⭐ Stars 少ない順" },
      { key: "forks_desc", label: "🍴 Forks 多い順" },
      { key: "forks_asc",  label: "🍴 Forks 少ない順" },
    ];
    sortContainer.innerHTML = "";
    sorts.forEach(s => {
      const li = document.createElement("li");
      li.className = "sidebar-item" + (s.key === state.sort ? " active" : "");
      li.dataset.sort = s.key;
      li.textContent = s.label;
      sortContainer.appendChild(li);
    });
  }

  // 日付フィルター（月別アコーディオン）
  const dateContainer = document.getElementById("date-filter");
  dateContainer.innerHTML = "";

  const monthMap = new Map();
  allDates.forEach(d => {
    const dt = new Date(d);
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
      li.className = "sidebar-item";
      li.dataset.date = d;
      const dt = new Date(d);
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
}

// =============================================
// モバイルカテゴリタブバー（ソートフィルター）
// =============================================

const SORT_COLORS = {
  "stars_desc": "#f59e0b",
  "stars_asc":  "#fbbf24",
  "forks_desc": "#06b6d4",
  "forks_asc":  "#22d3ee",
};

function buildMobileCategoryBar() {
  const scroll = document.getElementById("mobile-cat-scroll");
  if (!scroll) return;
  scroll.innerHTML = "";

  const sorts = [
    { key: "stars_desc", label: "⭐ Stars 多い順" },
    { key: "stars_asc",  label: "⭐ Stars 少ない順" },
    { key: "forks_desc", label: "🍴 Forks 多い順" },
    { key: "forks_asc",  label: "🍴 Forks 少ない順" },
  ];

  sorts.forEach(s => {
    const btn = document.createElement("button");
    btn.className = "mob-cat-btn" + (s.key === state.sort ? " active" : "");
    btn.dataset.sort = s.key;
    btn.textContent = s.label;
    btn.style.background = SORT_COLORS[s.key] || "#64748b";
    scroll.appendChild(btn);
  });

  scroll.addEventListener("click", e => {
    const btn = e.target.closest(".mob-cat-btn");
    if (!btn) return;
    scroll.querySelectorAll(".mob-cat-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    state.sort = btn.dataset.sort;
    state.page = 1;
    render();
  });
}

function buildMobileDateDropdown() {
  const list = document.getElementById("mob-date-list");
  const btn = document.getElementById("mob-date-btn");
  const dropdown = document.getElementById("mob-date-dropdown");
  if (!list || !btn || !dropdown) return;

  const allItem = document.createElement("button");
  allItem.className = "mob-date-item active";
  allItem.dataset.date = "all";
  allItem.textContent = "すべて";
  list.appendChild(allItem);

  allDates.forEach(d => {
    const item = document.createElement("button");
    item.className = "mob-date-item";
    item.dataset.date = d;
    const dt = new Date(d);
    item.textContent = `${dt.getMonth() + 1}/${dt.getDate()}`;
    list.appendChild(item);
  });

  btn.addEventListener("click", () => {
    dropdown.classList.toggle("open");
    btn.classList.toggle("active");
  });

  list.addEventListener("click", e => {
    const item = e.target.closest(".mob-date-item");
    if (!item) return;
    list.querySelectorAll(".mob-date-item").forEach(i => i.classList.remove("active"));
    item.classList.add("active");
    state.date = item.dataset.date;
    state.page = 1;
    const label = document.getElementById("mob-date-label");
    if (label) label.textContent = item.dataset.date === "all" ? "日付" : item.textContent;
    dropdown.classList.remove("open");
    btn.classList.remove("active");
    render();
  });
}

function filterRepos() {
  const filtered = allTrending.filter(r => {
    if (state.date !== "all" && r.date !== state.date) return false;
    if (state.search) {
      const q = state.search.toLowerCase();
      if (!r.title.toLowerCase().includes(q) && !r.summary.toLowerCase().includes(q)) return false;
    }
    return true;
  });

  switch (state.sort) {
    case "stars_desc": return [...filtered].sort((a, b) => b.date.localeCompare(a.date) || (b.stars || 0) - (a.stars || 0));
    case "stars_asc":  return [...filtered].sort((a, b) => b.date.localeCompare(a.date) || (a.stars || 0) - (b.stars || 0));
    case "forks_desc": return [...filtered].sort((a, b) => b.date.localeCompare(a.date) || (b.forks || 0) - (a.forks || 0));
    case "forks_asc":  return [...filtered].sort((a, b) => b.date.localeCompare(a.date) || (a.forks || 0) - (b.forks || 0));
    default:           return filtered;
  }
}

function createCard(repo) {
  const a = document.createElement("a");
  a.href = repo.url;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  a.className = "article-card trending-card";

  const parts = repo.title.split("/");
  const owner = parts[0] || "";
  const repoName = parts[1] || repo.title;

  const desc = repo.summary || repo.githubDescription || "";
  const starsHtml = repo.stars != null
    ? `<span class="trending-stat">⭐ ${formatNum(repo.stars)}</span>` : "";
  const forksHtml = repo.forks != null
    ? `<span class="trending-stat">🍴 ${formatNum(repo.forks)}</span>` : "";
  const langHtml = repo.language
    ? `<span class="trending-lang">${escHtml(repo.language)}</span>` : "";
  const hotHtml = (repo.trendingDays >= 2)
    ? `<span class="trending-hot">🔥 ${repo.trendingDays}日連続</span>` : "";

  a.innerHTML = `
    <div class="card-body">
      <div class="trending-repo-name">
        <span class="trending-owner">${escHtml(owner)}</span>
        <span class="trending-sep">/</span>
        <span class="trending-repo">${escHtml(repoName)}</span>
      </div>
      ${desc ? `<div class="card-summary">${escHtml(desc)}</div>` : ""}
      <div class="trending-stats">
        ${hotHtml}${starsHtml}${forksHtml}${langHtml}
      </div>
    </div>
  `;

  return a;
}

function formatNum(n) {
  if (n >= 1000) return (n / 1000).toFixed(1) + "k";
  return String(n);
}

function escHtml(str) {
  return (str || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function render() {
  const filtered = filterRepos();
  const visible = filtered.slice(0, state.page * PAGE_SIZE);
  const hasMore = visible.length < filtered.length;

  const hotCount = filtered.filter(r => r.trendingDays >= 2).length;
  const statsEl = document.getElementById("stats-bar");
  statsEl.innerHTML = `
    <span class="stats-item">🌟 GitHub Trending <strong>${filtered.length}件</strong></span>
    ${hotCount > 0 ? `<span class="stats-sep">|</span><span class="stats-item">🔥 連続ランクイン <strong>${hotCount}件</strong></span>` : ""}
  `;

  const container = document.getElementById("articles-container");
  container.innerHTML = "";

  if (visible.length === 0) {
    container.innerHTML = `
      <div id="empty-state">
        <div class="empty-icon">🔍</div>
        <div>リポジトリが見つかりませんでした</div>
      </div>`;
    document.getElementById("load-more-wrapper").style.display = "none";
    return;
  }

  // 日付グルーピング
  let currentDate = null;
  let dateCards = null;

  visible.forEach(repo => {
    if (repo.date !== currentDate) {
      currentDate = repo.date;
      const countForDate = filtered.filter(r => r.date === currentDate).length;
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

      dateCards = document.createElement("div");
      dateCards.className = "article-cards-grid";
      dateGroup.appendChild(dateCards);

      container.appendChild(dateGroup);
    }
    dateCards.appendChild(createCard(repo));
  });

  const loadMoreWrapper = document.getElementById("load-more-wrapper");
  if (hasMore) {
    loadMoreWrapper.style.display = "block";
    document.getElementById("load-more-btn").textContent =
      `もっと見る (残り${filtered.length - visible.length}件)`;
  } else {
    loadMoreWrapper.style.display = "none";
  }
}

function setupEvents() {
  document.getElementById("sort-filter")?.addEventListener("click", e => {
    const item = e.target.closest(".sidebar-item");
    if (!item) return;
    document.querySelectorAll("#sort-filter .sidebar-item").forEach(i => i.classList.remove("active"));
    item.classList.add("active");
    state.sort = item.dataset.sort;
    state.page = 1;
    render();
  });

  document.getElementById("date-filter").addEventListener("click", e => {
    const item = e.target.closest(".sidebar-item");
    if (!item) return;
    document.querySelectorAll("#date-filter .sidebar-item").forEach(i => i.classList.remove("active"));
    item.classList.add("active");
    state.date = item.dataset.date;
    state.page = 1;
    render();
  });

  document.getElementById("search-input").addEventListener("input", e => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.search = e.target.value.trim();
      state.page = 1;
      render();
    }, 300);
  });

  document.getElementById("load-more-btn").addEventListener("click", () => {
    state.page++;
    render();
  });

  const sidebarToggle = document.getElementById("sidebar-toggle");
  const sidebar = document.getElementById("sidebar");
  if (sidebarToggle) {
    sidebarToggle.addEventListener("click", () => {
      sidebar.classList.toggle("open");
    });
  }

  sidebar.addEventListener("click", e => {
    if (e.target.closest(".sidebar-item") && window.innerWidth <= 768) {
      sidebar.classList.remove("open");
    }
  });
}

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

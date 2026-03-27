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
  dateContainer.innerHTML = `<li class="sidebar-item active" data-date="all">All</li>`;

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
    case "stars_desc": return [...filtered].sort((a, b) => (b.stars || 0) - (a.stars || 0));
    case "stars_asc":  return [...filtered].sort((a, b) => (a.stars || 0) - (b.stars || 0));
    case "forks_desc": return [...filtered].sort((a, b) => (b.forks || 0) - (a.forks || 0));
    case "forks_asc":  return [...filtered].sort((a, b) => (a.forks || 0) - (b.forks || 0));
    default:           return filtered; // date順（元の順序）
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

  document.getElementById("stats-bar").textContent =
    `GitHub Trending — ${filtered.length}件表示中 (全${allTrending.length}件)`;

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

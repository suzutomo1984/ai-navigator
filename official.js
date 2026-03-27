/* =============================================
   AI Navigator - 公式リリースページ
   ============================================= */

const PAGE_SIZE = 50;

// 公式ソース → 会社グループのマッピング（parse_news.py の OFFICIAL_SOURCES と一致させること）
const SOURCE_GROUPS = {
  "OpenAI":     ["OpenAI Blog", "OpenAI SDK Releases", "OpenAI Node.js SDK Releases"],
  "Google":     ["Google AI Blog", "Google GenAI SDK Releases", "Google DeepMind Blog", "Gemini Blog"],
  "Anthropic":  ["Claude Code Releases", "Anthropic SDK Releases", "Anthropic TypeScript SDK Releases", "Anthropic News"],
  "Microsoft":  ["Microsoft Foundry Blog"],
  "MCP":        ["MCP Specification Releases", "MCP Python SDK Releases"],
  "LangChain":  ["LangChain Releases"],
  "LlamaIndex": ["LlamaIndex Releases"],
  "Ollama":     ["Ollama Releases"],
  "CrewAI":     ["CrewAI Releases"],
  "vLLM":       ["vLLM Releases"],
  "LiteLLM":    ["LiteLLM Releases"],
  "Dify":       ["Dify Releases"],
  "Flowise":    ["Flowise Releases"],
};

const state = {
  date: "all",
  company: "all",
  search: "",
  page: 1,
};

let allArticles = [];
let allDates = [];
let allCategories = [];
let searchTimer = null;

async function loadData() {
  const res = await fetch("articles.json");
  const data = await res.json();

  allArticles = data.articles || [];
  allDates = data.dates || [];
  allCategories = data.categories || [];

  buildSidebarFilters();
  render();
}

function buildSidebarFilters() {
  // 会社フィルター（公式記事に存在するグループのみ表示）
  const officialArticles = allArticles.filter(a => a.isOfficial);
  const companyList = document.getElementById("company-filter");
  companyList.innerHTML = `<li class="sidebar-item active" data-company="all">ALL</li>`;
  Object.entries(SOURCE_GROUPS).forEach(([company, sources]) => {
    const count = officialArticles.filter(a => sources.includes(a.source)).length;
    if (count === 0) return;
    const li = document.createElement("li");
    li.className = "sidebar-item";
    li.dataset.company = company;
    li.textContent = company;
    companyList.appendChild(li);
  });

  // 日付フィルター（月別アコーディオン）
  const dateContainer = document.getElementById("date-filter");
  dateContainer.innerHTML = `<li class="sidebar-item active" data-date="all">All</li>`;

  const validDates = allDates.filter(d => d.status === "ok" && d.articleCount > 0);

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
      li.className = "sidebar-item";
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
}

function filterArticles() {
  return allArticles.filter(a => {
    if (!a.isOfficial) return false;
    if (state.company !== "all") {
      const sources = SOURCE_GROUPS[state.company] || [];
      if (!sources.includes(a.source)) return false;
    }
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

function sortArticles(articles) {
  return [...articles].sort((a, b) => {
    if (a.date !== b.date) return b.date.localeCompare(a.date);
    return a.id.localeCompare(b.id);
  });
}

function createCard(article) {
  const a = document.createElement("a");
  a.href = article.url || "#";
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  a.className = "article-card";

  const categoryLabel = allCategories.find(c => c.id === article.category);
  const catText = categoryLabel ? `${categoryLabel.label}` : article.category;

  const sourceBadge = article.source
    ? `<span class="card-badge">${escHtml(article.source)}</span>`
    : "";

  const catBadge = `<span class="card-badge">${escHtml(catText)}</span>`;
  const officialBadge = `<span class="card-badge official-badge">📢 公式</span>`;

  const thumbHtml = article.thumbnail
    ? `<div class="card-thumb"><img src="${article.thumbnail}" alt="" loading="lazy" onerror="this.parentElement.style.display='none'"></div>`
    : "";

  a.innerHTML = `
    ${thumbHtml}
    <div class="card-body">
      <div class="card-header">
        <div class="card-title">${escHtml(article.title)}</div>
      </div>
      <div class="card-meta">
        ${sourceBadge}
        ${catBadge}
        ${officialBadge}
      </div>
      ${article.summary ? `<div class="card-summary">${escHtml(article.summary)}</div>` : ""}
    </div>
  `;

  return a;
}

function escHtml(str) {
  return (str || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function render() {
  const filtered = filterArticles();
  const sorted = sortArticles(filtered);
  const visible = sorted.slice(0, state.page * PAGE_SIZE);
  const hasMore = visible.length < sorted.length;

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

      dateCards = document.createElement("div");
      dateCards.className = "article-cards-grid";
      dateGroup.appendChild(dateCards);

      container.appendChild(dateGroup);
    }
    dateCards.appendChild(createCard(article));
  });

  const loadMoreWrapper = document.getElementById("load-more-wrapper");
  if (hasMore) {
    loadMoreWrapper.style.display = "block";
    document.getElementById("load-more-btn").textContent =
      `もっと見る (残り${sorted.length - visible.length}件)`;
  } else {
    loadMoreWrapper.style.display = "none";
  }
}

function setupEvents() {
  document.getElementById("company-filter").addEventListener("click", e => {
    const item = e.target.closest(".sidebar-item");
    if (!item) return;
    document.querySelectorAll("#company-filter .sidebar-item").forEach(i => i.classList.remove("active"));
    item.classList.add("active");
    state.company = item.dataset.company;
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

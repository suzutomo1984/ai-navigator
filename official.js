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
  buildMobileCategoryBar();
  buildMobileDateDropdown();
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

// =============================================
// モバイルカテゴリタブバー（会社フィルター）
// =============================================

const COMPANY_COLORS = {
  "all":        "#3b82f6",
  "OpenAI":     "#10a37f",
  "Google":     "#ea4335",
  "Anthropic":  "#d97706",
  "Microsoft":  "#0078d4",
  "MCP":        "#8b5cf6",
  "LangChain":  "#16a34a",
  "LlamaIndex": "#6366f1",
  "Ollama":     "#64748b",
  "CrewAI":     "#ec4899",
  "vLLM":       "#f59e0b",
  "LiteLLM":    "#06b6d4",
  "Dify":       "#7c3aed",
  "Flowise":    "#059669",
};

function buildMobileCategoryBar() {
  const scroll = document.getElementById("mobile-cat-scroll");
  if (!scroll) return;
  scroll.innerHTML = "";

  const officialArticles = allArticles.filter(a => a.isOfficial);

  const allBtn = document.createElement("button");
  allBtn.className = "mob-cat-btn active";
  allBtn.dataset.company = "all";
  allBtn.textContent = "ALL";
  allBtn.style.background = COMPANY_COLORS["all"];
  scroll.appendChild(allBtn);

  Object.entries(SOURCE_GROUPS).forEach(([company, sources]) => {
    const count = officialArticles.filter(a => sources.includes(a.source)).length;
    if (count === 0) return;
    const btn = document.createElement("button");
    btn.className = "mob-cat-btn";
    btn.dataset.company = company;
    btn.textContent = company;
    btn.style.background = COMPANY_COLORS[company] || "#64748b";
    scroll.appendChild(btn);
  });

  scroll.addEventListener("click", e => {
    const btn = e.target.closest(".mob-cat-btn");
    if (!btn) return;
    scroll.querySelectorAll(".mob-cat-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    state.company = btn.dataset.company;
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

  const validDates = allDates.filter(d => d.status === "ok" && d.articleCount > 0);
  validDates.forEach(d => {
    const item = document.createElement("button");
    item.className = "mob-date-item";
    item.dataset.date = d.date;
    const dt = new Date(d.date);
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

function openModal(article) {
  const modal = document.getElementById("article-modal");
  const categoryLabel = allCategories.find(c => c.id === article.category);
  const catText = categoryLabel ? categoryLabel.label : article.category;

  const thumbWrap = document.getElementById("modal-thumb-wrap");
  if (article.thumbnail) {
    thumbWrap.innerHTML = `<img src="${article.thumbnail}" alt="" onerror="this.parentElement.style.display='none'">`;
    thumbWrap.style.display = "block";
  } else {
    thumbWrap.innerHTML = "";
    thumbWrap.style.display = "none";
  }

  document.getElementById("modal-meta").innerHTML = `
    ${article.source ? `<span class="card-badge">${escHtml(article.source)}</span>` : ""}
    <span class="card-badge">${escHtml(catText)}</span>
    <span class="card-badge official-badge">📢 公式</span>
    ${article.date ? `<span class="card-date">${article.date.slice(5).replace("-", "/")}</span>` : ""}
  `;

  document.getElementById("modal-title").textContent = article.title || "";
  document.getElementById("modal-summary").textContent = article.summary || "（要約なし）";
  document.getElementById("modal-read-btn").href = article.url || "#";

  modal.setAttribute("aria-hidden", "false");
  modal.classList.add("open");
  document.body.style.overflow = "hidden";
  document.documentElement.style.overflow = "hidden";
}

function closeModal() {
  const modal = document.getElementById("article-modal");
  modal.classList.remove("open");
  modal.setAttribute("aria-hidden", "true");
  document.body.style.overflow = "";
  document.documentElement.style.overflow = "";
}

function createCard(article) {
  const card = document.createElement("div");
  card.className = "article-card";

  const categoryLabel = allCategories.find(c => c.id === article.category);
  const catText = categoryLabel ? `${categoryLabel.label}` : article.category;

  const sourceBadge = article.source
    ? `<span class="card-badge">${escHtml(article.source)}</span>`
    : "";

  const catBadge = `<span class="card-badge">${escHtml(catText)}</span>`;
  const officialBadge = `<span class="card-badge official-badge">📢 公式</span>`;
  const dateBadge = article.date
    ? `<span class="card-date">${article.date.slice(5).replace("-", "/")}</span>`
    : "";

  const thumbHtml = article.thumbnail
    ? `<div class="card-thumb"><img src="${article.thumbnail}" alt="" loading="lazy" onerror="this.parentElement.style.display='none'"></div>`
    : "";

  card.innerHTML = `
    ${thumbHtml}
    <div class="card-body">
      <div class="card-header">
        <div class="card-title">${escHtml(article.title)}</div>
      </div>
      <div class="card-meta">
        ${sourceBadge}
        ${catBadge}
        ${officialBadge}
        ${dateBadge}
      </div>
      ${article.summary ? `<div class="card-summary">${escHtml(article.summary)}</div>` : ""}
    </div>
  `;

  card.addEventListener("click", () => openModal(article));

  return card;
}

function escHtml(str) {
  return (str || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function render() {
  const filtered = filterArticles();
  const sorted = sortArticles(filtered);
  const visible = sorted.slice(0, state.page * PAGE_SIZE);
  const hasMore = visible.length < sorted.length;

  const companies = Object.entries(SOURCE_GROUPS)
    .map(([company, sources]) => {
      const count = filtered.filter(a => sources.includes(a.source)).length;
      return count > 0 ? `${company} ${count}` : null;
    })
    .filter(Boolean)
    .slice(0, 4)
    .join(" / ");
  const statsEl = document.getElementById("stats-bar");
  statsEl.innerHTML = `
    <span class="stats-item">📢 公式リリース <strong>${filtered.length}件</strong></span>
    ${companies ? `<span class="stats-sep">|</span><span class="stats-item stats-companies">${companies}</span>` : ""}
  `;

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
  document.getElementById("modal-close-btn").addEventListener("click", closeModal);
  document.getElementById("article-modal").addEventListener("click", e => {
    if (e.target === e.currentTarget) closeModal();
  });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") closeModal();
  });

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

// =============================================
// スワイプでカテゴリ切替（モバイル・ページめくりアニメーション）
// =============================================

function setupSwipe() {
  if (window.innerWidth > 768) return;

  const container = document.getElementById("articles-container");
  let startX = 0, startY = 0, currentX = 0;
  let isSwiping = false;
  let isAnimating = false;

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
    startX = e.touches[0].clientX;
    startY = e.touches[0].clientY;
    currentX = 0;
    isSwiping = false;
  }, { passive: true });

  document.addEventListener("touchmove", e => {
    if (isAnimating) return;
    const dx = e.touches[0].clientX - startX;
    const dy = e.touches[0].clientY - startY;
    if (!isSwiping && Math.abs(dy) > Math.abs(dx)) return;
    if (Math.abs(dx) > 8) {
      isSwiping = true;
      currentX = dx;
      const resist = Math.min(Math.abs(dx), 80) / Math.abs(dx);
      container.style.transform = `translateX(${dx * resist * 0.4}px)`;
      container.style.transition = "none";
      container.style.opacity = `${1 - Math.min(Math.abs(dx) / 300, 0.3)}`;
    }
  }, { passive: true });

  document.addEventListener("touchend", e => {
    if (!isSwiping || isAnimating) {
      container.style.transform = "";
      container.style.transition = "";
      container.style.opacity = "";
      isSwiping = false;
      return;
    }

    const dx = e.changedTouches[0].clientX - startX;
    isSwiping = false;

    if (Math.abs(dx) < 50) {
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

    container.style.transition = "transform 0.22s ease-in, opacity 0.22s ease-in";
    container.style.transform = `translateX(${dir * 100}%)`;
    container.style.opacity = "0";

    setTimeout(() => {
      btns.forEach(b => b.classList.remove("active"));
      btns[nextIdx].classList.add("active");
      btns[nextIdx].scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
      state.company = btns[nextIdx].dataset.company;
      state.page = 1;
      render();

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

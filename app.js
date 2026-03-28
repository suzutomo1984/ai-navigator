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

  // 日付フィルター（月別アコーディオン）
  const dateContainer = document.getElementById("date-filter");
  dateContainer.innerHTML = `<li class="sidebar-item active" data-date="all">All</li>`;

  const validDates = allDates.filter(d => d.status === "ok" && d.articleCount > 0);

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
// モバイルカテゴリタブバー構築
// =============================================

// カテゴリごとのタブカラー
const CAT_COLORS = {
  "all":          "#3b82f6",
  "ai-agent":     "#8b5cf6",
  "dev-tools":    "#06b6d4",
  "obsidian-pkm": "#10b981",
  "no-code":      "#f59e0b",
  "efficiency":   "#ef4444",
  "marketing":    "#ec4899",
  "official":     "#6366f1",
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
    render();
  });
}

function buildMobileDateDropdown() {
  const list = document.getElementById("mob-date-list");
  const btn = document.getElementById("mob-date-btn");
  const dropdown = document.getElementById("mob-date-dropdown");
  if (!list || !btn || !dropdown) return;

  // 「すべて」
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

  // 日付ボタンでドロップダウン開閉
  btn.addEventListener("click", () => {
    dropdown.classList.toggle("open");
    btn.classList.toggle("active");
  });

  // 日付アイテム選択
  list.addEventListener("click", e => {
    const item = e.target.closest(".mob-date-item");
    if (!item) return;
    list.querySelectorAll(".mob-date-item").forEach(i => i.classList.remove("active"));
    item.classList.add("active");
    state.date = item.dataset.date;
    state.page = 1;
    // ラベル更新
    const label = document.getElementById("mob-date-label");
    if (label) label.textContent = item.dataset.date === "all" ? "日付" : item.textContent;
    dropdown.classList.remove("open");
    btn.classList.remove("active");
    render();
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

function openModal(article) {
  const modal = document.getElementById("article-modal");
  const categoryLabel = allCategories.find(c => c.id === article.category);
  const catText = categoryLabel ? categoryLabel.label : article.category;

  // サムネイル
  const thumbWrap = document.getElementById("modal-thumb-wrap");
  if (article.thumbnail) {
    thumbWrap.innerHTML = `<img src="${article.thumbnail}" alt="" onerror="this.parentElement.style.display='none'">`;
    thumbWrap.style.display = "block";
  } else {
    thumbWrap.innerHTML = "";
    thumbWrap.style.display = "none";
  }

  // メタ情報
  const officialBadge = article.isOfficial ? `<span class="card-badge official-badge">📢 公式</span>` : "";
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

function createCard(article, isRanking = false) {
  const card = document.createElement("div");
  card.className = "article-card";

  if (article.isPick) {
    card.classList.add(article.pickPriority === "must-read" ? "pick-must" : "pick-check");
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

  const sourceBadge = article.source
    ? `<span class="card-badge">${escHtml(article.source)}</span>`
    : "";

  const catBadge = `<span class="card-badge">${escHtml(catText)}</span>`;
  const officialBadge = article.isOfficial ? `<span class="card-badge official-badge">📢 公式</span>` : "";
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
        ${pickBadge}
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
  const todayStr = allDates.length > 0 ? allDates[0].date : null;
  const todayCount = todayStr ? filtered.filter(a => a.date === todayStr).length : 0;
  const mustCount = allArticles.filter(a => a.isPick && a.pickPriority === "must-read").length;
  const checkCount = allArticles.filter(a => a.isPick && a.pickPriority !== "must-read").length;
  const statsEl = document.getElementById("stats-bar");
  statsEl.innerHTML = `
    <span class="stats-item">📰 ${filtered.length}件表示中</span>
    <span class="stats-sep">|</span>
    <span class="stats-item">本日 <strong>${todayCount}件</strong></span>
    ${mustCount > 0 ? `<span class="stats-sep">|</span><span class="stats-item">🔴マスト <strong>${mustCount}</strong></span>` : ""}
    ${checkCount > 0 ? `<span class="stats-sep">|</span><span class="stats-item">🟡チェック <strong>${checkCount}</strong></span>` : ""}
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
              <span class="summary-date">📅 ${mm}/${dd} の AI ニュース</span>
              <span class="summary-count">${dateInfo.articleCount || 0}件</span>
            </div>
            <div class="summary-text">${escHtml(dateInfo.dailySummary)}</div>
          `;
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
// スワイプでカテゴリ切替（モバイル・ページめくりアニメーション）
// =============================================

function setupSwipe() {
  if (window.innerWidth > 768) return;

  const container = document.getElementById("articles-container");
  const main = document.getElementById("main");
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
      render();

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

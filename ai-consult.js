(() => {
  "use strict";

  const AI_CONSULT_PROMPT = `AI Navigator（ai-navigator.dev）で、最新のAIニュースを調べて要約してください。
知りたいテーマ：
期間：`;

  const AI_SERVICES = [
    { id: "chatgpt", name: "ChatGPT", baseUrl: "https://chatgpt.com/", promptParam: "q" },
    { id: "gemini", name: "Gemini", baseUrl: "https://gemini.google.com/app", promptParam: null },
    { id: "claude", name: "Claude", baseUrl: "https://claude.ai/new", promptParam: "q" },
    { id: "perplexity", name: "Perplexity", baseUrl: "https://www.perplexity.ai/search", promptParam: "q" },
  ];

  const AI_SERVICE_ICONS = {
    chatgpt: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.2a4.1 4.1 0 0 1 7 3 4.1 4.1 0 0 1 1.1 7.8 4.1 4.1 0 0 1-5.9 5.2A4.1 4.1 0 0 1 7 18a4.1 4.1 0 0 1-3-7.1A4.1 4.1 0 0 1 8.9 5.2 4 4 0 0 1 12 3.2Z"/><path d="m8.2 9.8 3.8-2.2 3.8 2.2v4.4L12 16.4l-3.8-2.2Z"/></svg>`,
    gemini: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2c.7 5.7 4.3 9.3 10 10-5.7.7-9.3 4.3-10 10-.7-5.7-4.3-9.3-10-10 5.7-.7 9.3-4.3 10-10Z"/></svg>`,
    claude: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v18M4.2 7.5l15.6 9M4.2 16.5l15.6-9M3 12h18"/></svg>`,
    perplexity: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5h14v14H5zM12 2v20M5 5l14 14M19 5 5 19M2 12h20"/></svg>`,
  };

  function buildAiUrl(service, prompt) {
    if (!service.promptParam) return service.baseUrl;
    const url = new URL(service.baseUrl);
    url.searchParams.set(service.promptParam, prompt);
    return url.toString();
  }

  const root = document.createElement("div");
  root.className = "ai-consult";
  root.innerHTML = `
    <div class="ai-consult-menu" id="ai-consult-menu" role="menu" aria-label="相談先のAIを選択" hidden>
      <p class="ai-consult-description">普段使ってるAIに最新AIニュースを聞けます</p>
      <div class="ai-consult-services"></div>
    </div>
    <button class="ai-consult-button" type="button" aria-expanded="false" aria-haspopup="menu" aria-controls="ai-consult-menu" aria-label="AI相談メニューを開く">
      <svg class="ai-consult-button-icon ai-consult-button-icon-open" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5h14v11H9l-4 3v-3H5z"/><path d="M12 7.5c.3 2.1 1.4 3.2 3.5 3.5-2.1.3-3.2 1.4-3.5 3.5-.3-2.1-1.4-3.2-3.5-3.5 2.1-.3 3.2-1.4 3.5-3.5Z"/></svg>
      <span class="ai-consult-button-icon ai-consult-button-icon-close" aria-hidden="true">×</span>
      <span>AI相談</span>
    </button>
    <div class="ai-consult-toast" role="status" aria-live="polite" hidden></div>`;

  const menu = root.querySelector(".ai-consult-menu");
  const servicesContainer = root.querySelector(".ai-consult-services");
  const button = root.querySelector(".ai-consult-button");
  const toast = root.querySelector(".ai-consult-toast");
  let toastTimer;

  function showToast(message) {
    window.clearTimeout(toastTimer);
    toast.textContent = message;
    toast.hidden = false;
    toastTimer = window.setTimeout(() => {
      toast.hidden = true;
    }, 4000);
  }

  function openMenu() {
    menu.hidden = false;
    root.classList.add("is-open");
    button.setAttribute("aria-expanded", "true");
    button.setAttribute("aria-label", "AI相談メニューを閉じる");
  }

  function closeMenu() {
    menu.hidden = true;
    root.classList.remove("is-open");
    button.setAttribute("aria-expanded", "false");
    button.setAttribute("aria-label", "AI相談メニューを開く");
  }

  async function onServiceClick(service) {
    if (typeof gtag === "function") {
      gtag("event", "ai_consult_click", {
        ai_service: service.id,
        page_path: location.pathname,
      });
    }
    if (!service.promptParam) {
      try {
        await navigator.clipboard.writeText(AI_CONSULT_PROMPT);
        showToast(`相談内容をコピーしました。${service.name} に貼り付けて送信してください`);
      } catch {
        showToast(`${service.name} を開きました。相談内容を入力してください`);
      }
    }
    closeMenu();
  }

  AI_SERVICES.forEach(service => {
    const item = document.createElement("a");
    item.className = "ai-consult-service";
    item.href = buildAiUrl(service, AI_CONSULT_PROMPT);
    item.target = "_blank";
    item.rel = "noopener noreferrer";
    item.setAttribute("role", "menuitem");
    item.setAttribute("aria-label", `${service.name}で最新AIニュースを聞く`);
    item.innerHTML = `<span class="ai-consult-service-icon ai-consult-service-icon-${service.id}">${AI_SERVICE_ICONS[service.id]}</span><span>${service.name}</span>`;
    item.addEventListener("click", () => onServiceClick(service));
    servicesContainer.appendChild(item);
  });

  button.addEventListener("click", () => {
    if (button.getAttribute("aria-expanded") === "true") {
      closeMenu();
    } else {
      openMenu();
    }
  });

  document.addEventListener("click", event => {
    if (!root.contains(event.target)) closeMenu();
  });

  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && button.getAttribute("aria-expanded") === "true") {
      closeMenu();
      button.focus();
    }
  });

  document.body.appendChild(root);
})();

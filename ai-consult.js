(() => {
  "use strict";

  const AI_SERVICES = Object.freeze([
    { id: "chatgpt", name: "ChatGPT", baseUrl: "https://chatgpt.com/", promptParam: "q" },
    { id: "google_ai_mode", name: "Google AI Mode", baseUrl: "https://www.google.com/search?udm=50", promptParam: "q" },
    { id: "claude", name: "Claude", baseUrl: "https://claude.ai/new", promptParam: "q" },
    { id: "perplexity", name: "Perplexity", baseUrl: "https://www.perplexity.ai/search", promptParam: "q" },
  ]);

  const AI_SERVICE_ICONS = {
    chatgpt: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.2a4.1 4.1 0 0 1 7 3 4.1 4.1 0 0 1 1.1 7.8 4.1 4.1 0 0 1-5.9 5.2A4.1 4.1 0 0 1 7 18a4.1 4.1 0 0 1-3-7.1A4.1 4.1 0 0 1 8.9 5.2 4 4 0 0 1 12 3.2Z"/><path d="m8.2 9.8 3.8-2.2 3.8 2.2v4.4L12 16.4l-3.8-2.2Z"/></svg>`,
    google_ai_mode: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2c.7 5.7 4.3 9.3 10 10-5.7.7-9.3 4.3-10 10-.7-5.7-4.3-9.3-10-10 5.7-.7 9.3-4.3 10-10Z"/></svg>`,
    claude: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v18M4.2 7.5l15.6 9M4.2 16.5l15.6-9M3 12h18"/></svg>`,
    perplexity: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5h14v14H5zM12 2v20M5 5l14 14M19 5 5 19M2 12h20"/></svg>`,
  };

  function buildConsultPrompt(article) {
    return `【前提】AIに入力する情報は、利用者自身の責任で選別します。

AI Navigator（ai-navigator.dev）で紹介されていた「${article.title || ""}」というAIニュースについて、
概要と、私の場合どう活かせるかを教えてください。

私の状況（業種・役割・関心）：`;
  }

  function buildAiUrl(service, prompt) {
    const url = new URL(service.baseUrl);
    url.searchParams.set(service.promptParam, prompt);
    return url.toString();
  }

  function trackConsult(serviceId, article) {
    if (typeof gtag === "function") {
      gtag("event", "ai_consult_click", {
        ai_service: serviceId,
        item_name: article.title || "",
        page_path: location.pathname,
      });
    }
  }

  function render(article, readBtn) {
    if (!readBtn) return null;

    // openModalのたびに前のカードを破棄して再生成し、記事別URLとハンドラを更新する。
    readBtn.parentElement?.querySelector(".ai-consult-card")?.remove();

    const prompt = buildConsultPrompt(article);
    const card = document.createElement("section");
    card.className = "ai-consult-card";
    card.setAttribute("aria-labelledby", "ai-consult-heading");
    card.innerHTML = `
      <p class="ai-consult-label">ASK AI</p>
      <h3 class="ai-consult-heading" id="ai-consult-heading">「私の場合は？」を、普段お使いのAIに相談</h3>
      <p class="ai-consult-description">ボタンを押すと、この記事を踏まえて「自分の場合はどうすべきか」を聞ける相談文が各AIに渡ります<br>（ChatGPTとClaudeは入力欄にセット、Google AI ModeとPerplexityは自動送信。環境により挙動が変わることがあります）。<br>相談は各AIサービス上で行われ、リンク先で入力した内容を当サイトが取得することはありません。</p>
      <div class="ai-consult-services"></div>
      <button class="ai-consult-copy" type="button" aria-label="AI相談用プロンプトをコピー">
        <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="8" width="11" height="11" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></svg>
        <span>プロンプトをコピー</span>
      </button>
      <div class="ai-consult-toast" role="status" aria-live="polite" hidden></div>`;

    const servicesContainer = card.querySelector(".ai-consult-services");
    const toast = card.querySelector(".ai-consult-toast");
    let toastTimer;

    function showToast(message) {
      window.clearTimeout(toastTimer);
      toast.textContent = message;
      toast.hidden = false;
      toastTimer = window.setTimeout(() => {
        toast.hidden = true;
      }, 4000);
    }

    AI_SERVICES.forEach(service => {
      const link = document.createElement("a");
      link.className = "ai-consult-service";
      link.href = buildAiUrl(service, prompt);
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.setAttribute("aria-label", `${service.name}でこの記事について相談`);
      link.innerHTML = `<span class="ai-consult-service-icon ai-consult-service-icon-${service.id}">${AI_SERVICE_ICONS[service.id]}</span><span>${service.name}で相談</span>`;
      // カードは毎回再生成するが、onclick上書きにして多重登録の余地もなくす。
      link.onclick = event => {
        event.stopPropagation();
        trackConsult(service.id, article);
      };
      servicesContainer.appendChild(link);
    });

    const copyButton = card.querySelector(".ai-consult-copy");
    copyButton.onclick = async event => {
      event.stopPropagation();
      trackConsult("copy", article);
      try {
        await navigator.clipboard.writeText(prompt);
        showToast("プロンプトをコピーしました");
      } catch {
        showToast("コピーできませんでした。ブラウザの権限設定をご確認ください");
      }
    };

    readBtn.insertAdjacentElement("afterend", card);
    return card;
  }

  window.AiConsult = Object.freeze({ AI_SERVICES, buildAiUrl, buildConsultPrompt, render });
})();

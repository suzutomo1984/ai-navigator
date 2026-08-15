import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = fs.readFileSync(path.join(rootDir, "ai-consult.js"), "utf8");
const appSource = fs.readFileSync(path.join(rootDir, "app.js"), "utf8");
const officialSource = fs.readFileSync(path.join(rootDir, "official.js"), "utf8");
const style = fs.readFileSync(path.join(rootDir, "style.css"), "utf8");

class MockElement {
  constructor(tagName) {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.attributes = new Map();
    this.hidden = false;
    this.className = "";
  }

  set innerHTML(value) {
    this._innerHTML = value;
    if (this.className !== "ai-consult-card") return;
    const services = new MockElement("div");
    services.className = "ai-consult-services";
    const copy = new MockElement("button");
    copy.className = "ai-consult-copy";
    const toast = new MockElement("div");
    toast.className = "ai-consult-toast";
    toast.hidden = true;
    this.appendChild(services);
    this.appendChild(copy);
    this.appendChild(toast);
  }

  get innerHTML() { return this._innerHTML || ""; }
  get parentElement() { return this.parent || null; }

  appendChild(child) {
    this.children.push(child);
    child.parent = this;
    return child;
  }

  insertAdjacentElement(position, child) {
    assert.equal(position, "afterend");
    const index = this.parent.children.indexOf(this);
    this.parent.children.splice(index + 1, 0, child);
    child.parent = this.parent;
    return child;
  }

  remove() {
    if (!this.parent) return;
    this.parent.children = this.parent.children.filter(child => child !== this);
    this.parent = null;
  }

  querySelector(selector) {
    const wantedClass = selector.startsWith(".") ? selector.slice(1) : null;
    for (const child of this.children) {
      if (wantedClass && child.className.split(/\s+/).includes(wantedClass)) return child;
      const nested = child.querySelector(selector);
      if (nested) return nested;
    }
    return null;
  }

  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  getAttribute(name) { return this.attributes.get(name) ?? null; }
  contains(target) { return target === this || this.children.some(child => child.contains(target)); }
}

const analytics = [];
const clipboardWrites = [];
const document = { createElement: tagName => new MockElement(tagName) };
const context = {
  URL,
  document,
  location: { pathname: "/news" },
  navigator: { clipboard: { writeText: async value => clipboardWrites.push(value) } },
  gtag: (...args) => analytics.push(args),
  window: { clearTimeout() {}, setTimeout() { return 1; } },
};
context.window.window = context.window;
vm.createContext(context);
vm.runInContext(source, context, { filename: "ai-consult.js" });

const { AI_SERVICES, buildAiUrl, buildConsultPrompt, render } = context.window.AiConsult;
assert.equal(AI_SERVICES.length, 4);
assert.deepEqual(Array.from(AI_SERVICES, service => service.id), ["chatgpt", "google_ai_mode", "claude", "perplexity"]);

const articleA = {
  title: "テスト記事A",
  url: "https://external.example/article-a",
  summary: "プロンプトに含めてはいけない要約",
};
const articleB = {
  title: "別の記事B",
  url: "https://external.example/article-b",
  summary: "別の要約",
};
const promptA = buildConsultPrompt(articleA);
const promptB = buildConsultPrompt(articleB);

assert.ok(promptA.startsWith("【前提】AIに入力する情報は、利用者自身の責任で選別します。"));
assert.match(promptA, /ai-navigator\.dev/);
assert.match(promptA, /テスト記事A/);
assert.doesNotMatch(promptA, /external\.example|プロンプトに含めてはいけない要約/);
assert.notEqual(promptA, promptB, "記事を切り替えたらプロンプトも変わること");
assert.match(promptB, /別の記事B/);

for (const service of AI_SERVICES) {
  const url = new URL(buildAiUrl(service, promptA));
  assert.equal(url.searchParams.get("q"), promptA, `${service.id} must receive the prompt`);
}
const googleUrl = new URL(buildAiUrl(AI_SERVICES[1], promptA));
assert.equal(googleUrl.searchParams.get("udm"), "50");
assert.equal(googleUrl.searchParams.get("q"), promptA);

const modalContent = new MockElement("div");
const readBtn = new MockElement("a");
modalContent.appendChild(readBtn);
const cardA = render(articleA, readBtn);
assert.equal(modalContent.children.length, 2);
assert.equal(modalContent.children[1], cardA, "card must be inserted immediately after the read button");

const servicesA = cardA.querySelector(".ai-consult-services").children;
assert.equal(servicesA.length, 4);
assert.ok(servicesA.every(link => link.target === "_blank"));
assert.ok(servicesA.every(link => link.rel === "noopener noreferrer"));
assert.ok(servicesA.every(link => link.getAttribute("aria-label")?.includes("相談")));
assert.ok(servicesA.every(link => new URL(link.href).searchParams.get("q") === promptA));

let propagationStopped = false;
servicesA[0].onclick({ stopPropagation() { propagationStopped = true; } });
assert.equal(propagationStopped, true);
assert.equal(JSON.stringify(analytics.at(-1)), JSON.stringify(["event", "ai_consult_click", {
  ai_service: "chatgpt",
  item_name: articleA.title,
  page_path: "/news",
}]));

const copyA = cardA.querySelector(".ai-consult-copy");
await copyA.onclick({ stopPropagation() {} });
assert.equal(clipboardWrites.at(-1), promptA);
assert.equal(cardA.querySelector(".ai-consult-toast").hidden, false);
assert.match(cardA.querySelector(".ai-consult-toast").textContent, /コピーしました/);
assert.equal(analytics.at(-1)[2].ai_service, "copy");

const cardB = render(articleB, readBtn);
assert.equal(modalContent.children.length, 2, "previous card must be removed rather than duplicated");
assert.equal(modalContent.children[1], cardB);
assert.notEqual(cardA, cardB);
assert.ok(cardB.querySelector(".ai-consult-services").children.every(link => new URL(link.href).searchParams.get("q") === promptB));

context.navigator.clipboard.writeText = async () => { throw new Error("clipboard unavailable"); };
await cardB.querySelector(".ai-consult-copy").onclick({ stopPropagation() {} });
assert.match(cardB.querySelector(".ai-consult-toast").textContent, /コピーできませんでした/);

delete context.gtag;
servicesA[2].onclick({ stopPropagation() {} });

for (const htmlFile of ["index.html", "news.html", "official.html", "about.html"]) {
  const html = fs.readFileSync(path.join(rootDir, htmlFile), "utf8");
  assert.equal((html.match(/<script src="ai-consult\.js"><\/script>/g) || []).length, 1, `${htmlFile} must load ai-consult.js once`);
}

assert.match(appSource, /window\.AiConsult\?\.render\(article, readBtn\)/);
assert.match(officialSource, /window\.AiConsult\?\.render\(article, readBtn\)/);
assert.doesNotMatch(source, /document\.body\.appendChild/);
assert.match(source, /new URL\(service\.baseUrl\)/);
assert.match(source, /role="status" aria-live="polite"/);
assert.match(source, /aria-hidden="true"/);
assert.match(source, /リンク先で入力した内容を当サイトが取得することはありません/);

const consultCssStart = style.indexOf("/* =============================================\n   AI相談");
const consultCssEnd = style.indexOf(".top-section-heading h2 span", consultCssStart);
const consultCss = style.slice(consultCssStart, consultCssEnd);
assert.match(consultCss, /\.ai-consult-card\s*\{[^}]*width:\s*100%;[^}]*min-width:\s*0;/s);
assert.match(consultCss, /\.ai-consult-services\s*\{[^}]*flex-direction:\s*column;/s);
assert.match(consultCss, /@media \(max-width:\s*375px\)/);
assert.doesNotMatch(consultCss, /position:\s*fixed/);
assert.doesNotMatch(consultCss, /#[0-9a-f]{3,8}\b|rgba?\(/i, "AI consult CSS must use existing color variables");

console.log(JSON.stringify({
  services: AI_SERVICES.length,
  googleParams: Array.from(googleUrl.searchParams.keys()),
  cardCountAfterArticleSwitch: modalContent.children.length - 1,
  clipboardSuccessAndFailure: true,
  pagesLoadingScript: 4,
  responsiveWidth: 375,
}, null, 2));

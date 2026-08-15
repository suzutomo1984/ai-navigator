import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";


const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = fs.readFileSync(path.join(rootDir, "ai-consult.js"), "utf8");
const style = fs.readFileSync(path.join(rootDir, "style.css"), "utf8");


class MockElement {
  constructor(tagName) {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.attributes = new Map();
    this.handlers = new Map();
    this.hidden = false;
    this._className = "";
    this._innerHTML = "";
    this.classList = {
      add: name => this._setClasses([...this._classes(), name]),
      remove: name => this._setClasses([...this._classes()].filter(value => value !== name)),
      contains: name => this._classes().has(name),
    };
  }

  _classes() { return new Set(this._className.split(/\s+/).filter(Boolean)); }
  _setClasses(values) { this._className = [...new Set(values)].join(" "); }
  set className(value) { this._className = value; }
  get className() { return this._className; }

  set innerHTML(value) {
    this._innerHTML = value;
    if (this.className !== "ai-consult") return;
    const menu = new MockElement("div");
    menu.className = "ai-consult-menu";
    menu.hidden = true;
    const services = new MockElement("div");
    services.className = "ai-consult-services";
    menu.appendChild(services);
    const button = new MockElement("button");
    button.className = "ai-consult-button";
    button.setAttribute("aria-expanded", "false");
    const toast = new MockElement("div");
    toast.className = "ai-consult-toast";
    toast.hidden = true;
    this.appendChild(menu);
    this.appendChild(button);
    this.appendChild(toast);
  }
  get innerHTML() { return this._innerHTML; }

  appendChild(child) { this.children.push(child); child.parent = this; return child; }
  querySelector(selector) {
    const className = selector.startsWith(".") ? selector.slice(1) : null;
    for (const child of this.children) {
      if (className && child.classList.contains(className)) return child;
      const nested = child.querySelector(selector);
      if (nested) return nested;
    }
    return null;
  }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  getAttribute(name) { return this.attributes.get(name) ?? null; }
  addEventListener(type, callback) { this.handlers.set(type, callback); }
  dispatch(type, event = {}) { return this.handlers.get(type)?.({ target: this, ...event }); }
  contains(target) { return target === this || this.children.some(child => child.contains(target)); }
  focus() { this.focused = true; }
}


const documentHandlers = new Map();
const document = {
  body: new MockElement("body"),
  createElement: tagName => new MockElement(tagName),
  addEventListener(type, callback) { documentHandlers.set(type, callback); },
};
const analytics = [];
const clipboardWrites = [];
const context = {
  URL,
  clearTimeout,
  document,
  location: { pathname: "/news" },
  navigator: { clipboard: { writeText: async value => clipboardWrites.push(value) } },
  setTimeout,
  gtag: (...args) => analytics.push(args),
  window: { clearTimeout() {}, setTimeout() { return 1; } },
};
vm.createContext(context);
vm.runInContext(source, context, { filename: "ai-consult.js" });

const widget = document.body.children[0];
const menu = widget.querySelector(".ai-consult-menu");
const button = widget.querySelector(".ai-consult-button");
const toast = widget.querySelector(".ai-consult-toast");
const services = widget.querySelector(".ai-consult-services").children;

assert.equal(services.length, 4);
assert.deepEqual(services.map(item => item.target), ["_blank", "_blank", "_blank", "_blank"]);
assert.ok(services.every(item => item.rel === "noopener noreferrer"));
assert.ok(services.every(item => item.getAttribute("role") === "menuitem"));

const prompt = `AI Navigator（ai-navigator.dev）で、最新のAIニュースを調べて要約してください。
知りたいテーマ：
期間：`;
for (const index of [0, 2, 3]) {
  const url = new URL(services[index].href);
  assert.equal(url.searchParams.get("q"), prompt);
}
assert.equal(services[1].href, "https://gemini.google.com/app");
assert.equal(new URL(services[1].href).searchParams.has("q"), false);

button.dispatch("click");
assert.equal(menu.hidden, false);
assert.equal(button.getAttribute("aria-expanded"), "true");
assert.equal(widget.classList.contains("is-open"), true);
documentHandlers.get("click")({ target: new MockElement("main") });
assert.equal(menu.hidden, true);

button.dispatch("click");
documentHandlers.get("keydown")({ key: "Escape" });
assert.equal(menu.hidden, true);
assert.equal(button.focused, true);

button.dispatch("click");
services[0].dispatch("click");
assert.equal(menu.hidden, true);
assert.equal(JSON.stringify(analytics.at(-1)), JSON.stringify(["event", "ai_consult_click", { ai_service: "chatgpt", page_path: "/news" }]));

button.dispatch("click");
services[1].dispatch("click");
await new Promise(resolve => setTimeout(resolve, 0));
assert.equal(clipboardWrites.at(-1), prompt);
assert.equal(menu.hidden, true);
assert.equal(toast.hidden, false);
assert.match(toast.textContent, /相談内容をコピーしました。Gemini に貼り付けて送信してください/);
assert.equal(JSON.stringify(analytics.at(-1)), JSON.stringify(["event", "ai_consult_click", { ai_service: "gemini", page_path: "/news" }]));

context.navigator.clipboard.writeText = async () => { throw new Error("clipboard unavailable"); };
button.dispatch("click");
services[1].dispatch("click");
await new Promise(resolve => setTimeout(resolve, 0));
assert.match(toast.textContent, /Gemini を開きました。相談内容を入力してください/);

delete context.gtag;
button.dispatch("click");
services[2].dispatch("click");
assert.equal(menu.hidden, true, "service click must work without gtag");

for (const htmlFile of ["index.html", "news.html", "official.html", "about.html"]) {
  const html = fs.readFileSync(path.join(rootDir, htmlFile), "utf8");
  assert.equal((html.match(/<script src="ai-consult\.js"><\/script>/g) || []).length, 1, `${htmlFile} must load ai-consult.js once`);
}

const consultCss = style.slice(style.indexOf("/* =============================================\n   AI相談"), style.indexOf(".top-section-heading h2 span"));
assert.match(consultCss, /\.ai-consult\s*\{[^}]*position:\s*fixed;[^}]*right:\s*16px;[^}]*bottom:\s*calc\(16px \+ env\(safe-area-inset-bottom\)\);[^}]*z-index:\s*10001;/s);
assert.match(consultCss, /\.ai-consult-button\s*\{[^}]*height:\s*48px;/s);
assert.match(consultCss, /\.ai-consult-menu\s*\{[^}]*bottom:\s*calc\(100% \+ 12px\);[^}]*width:\s*min\(256px, calc\(100vw - 32px\)\);/s);
assert.match(consultCss, /@media print\s*\{\s*\.ai-consult\s*\{\s*display:\s*none;/s);
assert.doesNotMatch(consultCss, /#[0-9a-f]{3,8}\b|rgba?\(/i, "AI consult CSS must use existing color variables");
assert.match(source, /aria-haspopup="menu"/);
assert.match(source, /role="menu"/);
assert.match(source, /aria-hidden="true"/);
assert.match(source, /普段使ってるAIに最新AIニュースを聞けます/);

console.log(JSON.stringify({ services: services.length, clipboardWrites: clipboardWrites.length, analyticsEvents: analytics.length, pages: 4, responsiveMenuWidth: "min(256px, calc(100vw - 32px))" }, null, 2));

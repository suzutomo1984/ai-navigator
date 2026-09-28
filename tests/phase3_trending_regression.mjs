import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";


const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const appSource = fs.readFileSync(path.join(root, "app.js"), "utf8");
const indexSource = fs.readFileSync(path.join(root, "index.html"), "utf8");
const data = JSON.parse(fs.readFileSync(path.join(root, "articles.json"), "utf8"));
const trendingSection = { hidden: false };
const trendingElement = {
  innerHTML: "",
  closest(selector) {
    assert.equal(selector, ".top-trending-section");
    return trendingSection;
  },
};
const context = {
  console,
  document: {
    addEventListener() {},
    getElementById(id) { return id === "top-github-trending" ? trendingElement : null; },
  },
  window: {},
};
vm.createContext(context);
vm.runInContext(
  `${appSource}\n;globalThis.__phase3TestApi = { renderTopTrending, topTrendingRepos, renderLanding, setTrending(value) { allTrending = value; } };`,
  context,
  { filename: "app.js" },
);

const { renderTopTrending, topTrendingRepos, renderLanding, setTrending } = context.__phase3TestApi;
const repositories = [
  { title: "pipepipe/pipepipe", aiRelated: false, url: "https://github.com/pipepipe/pipepipe" },
  {
    title: "paperclipai/paperclip",
    jaName: "AIエージェント管理アプリ",
    summary: "複数のAIエージェントをまとめて管理できます。",
    workUse: "問い合わせ対応や資料作成のAIを一か所で管理できます。",
    audience: "ready",
    aiRelated: true,
    trendingDays: 1,
    stars: 100,
    language: "TypeScript",
    url: "https://github.com/paperclipai/paperclip",
  },
  {
    title: "owner/install-tool",
    jaName: "社内文書検索ツール",
    summary: "社内資料を検索するAIツールです。",
    workUse: "社内資料の確認時間を短縮できます。",
    audience: "install",
    aiRelated: true,
    trendingDays: 3,
    url: "https://github.com/owner/install-tool",
  },
  {
    title: "owner/dev-library",
    jaName: "AI連携ライブラリ",
    summary: "開発者がAI機能を組み込むための部品です。",
    workUse: "社内システムへのAI機能追加に使えます。",
    audience: "developer",
    aiRelated: true,
    url: "https://github.com/owner/dev-library",
  },
  { title: "owner/legacy-tool", summary: "旧形式の記事要約です。", url: "https://github.com/owner/legacy-tool" },
  { title: "owner/legacy-tool-2", summary: "もう一つの旧形式要約です。", url: "https://github.com/owner/legacy-tool-2" },
  { title: "owner/legacy-tool-3", summary: "7件目の旧形式要約です。", url: "https://github.com/owner/legacy-tool-3" },
  { title: "owner/legacy-tool-4", summary: "8件目の旧形式要約です。", url: "https://github.com/owner/legacy-tool-4" },
  { title: "owner/legacy-tool-5", summary: "9件目の旧形式要約です。", url: "https://github.com/owner/legacy-tool-5" },
  { title: "owner/legacy-tool-6", summary: "10件目の旧形式要約です。", url: "https://github.com/owner/legacy-tool-6" },
  { title: "owner/legacy-tool-7", summary: "11件目の旧形式要約です。", url: "https://github.com/owner/legacy-tool-7" },
  { title: "owner/over-limit", summary: "11件目は出しません。", url: "https://github.com/owner/over-limit" },
  { title: "owner/no-summary", summary: "", jaName: "", url: "https://github.com/owner/no-summary" },
];

const html = renderTopTrending(repositories);
assert.equal((html.match(/class="top-trending-item"/g) || []).length, 10);
assert.ok(html.includes("AIエージェント管理アプリ"));
assert.ok(html.includes("問い合わせ対応や資料作成のAIを一か所で管理できます。"));
assert.ok(html.includes("すぐ使える"));
assert.ok(html.includes("今日から話題"));
assert.ok(html.includes("要インストール"));
assert.ok(html.includes("3日連続"));
assert.ok(html.includes("開発者向け"));
assert.ok(html.includes("owner/legacy-tool ↗ GitHub（英語）"));
assert.ok(!html.includes("pipepipe/pipepipe"));
assert.ok(!html.includes("11件目は出しません"));
assert.ok(!html.includes("owner/no-summary"));
assert.ok(!html.includes("★ 100"));
assert.ok(!html.includes("TypeScript"));
assert.equal((topTrendingRepos(repositories).map(repo => repo.title).includes("pipepipe/pipepipe")), false);

const displayableRepos = repositories.filter(repo =>
  repo.aiRelated !== false && Boolean(String(repo.summary || "").trim() || String(repo.jaName || "").trim())
);
const sevenHtml = renderTopTrending(displayableRepos.slice(0, 7));
assert.equal((sevenHtml.match(/class="top-trending-item"/g) || []).length, 7);
const twelveRepos = displayableRepos.slice(0, 11).concat({
  ...displayableRepos[0],
  title: "owner/twelve",
  summary: "12件目の表示可能要約です。",
  url: "https://github.com/owner/twelve",
});
assert.equal(twelveRepos.length, 12);
assert.equal(topTrendingRepos(twelveRepos).length, 10);
assert.equal((renderTopTrending(twelveRepos).match(/class="top-trending-item"/g) || []).length, 10);

const legacyHtml = renderTopTrending([repositories[4]]);
assert.ok(legacyHtml.includes("owner/legacy-tool"));
assert.ok(legacyHtml.includes("旧形式の記事要約です。"));
assert.ok(!legacyHtml.includes("仕事では:"));
assert.ok(!legacyHtml.includes("開発者向け"));

setTrending(repositories.filter(repo => repo.aiRelated !== false));
renderLanding();
assert.equal(trendingSection.hidden, false);
assert.equal((trendingElement.innerHTML.match(/class="top-trending-item"/g) || []).length, 10);
setTrending([{ title: "unrelated/one", aiRelated: false }, { title: "unrelated/two", aiRelated: false }]);
renderLanding();
assert.equal(trendingSection.hidden, true);
assert.equal(trendingElement.innerHTML, "");

assert.equal((indexSource.match(/id=["']top-github-trending["']/g) || []).length, 1);
assert.ok(indexSource.includes("今、世界で話題のAIツール"));
assert.ok(indexSource.includes("エンジニアの間で急上昇中の無料ツール"));

const actualHtml = renderTopTrending(data.trending || []);
assert.ok((actualHtml.match(/class="top-trending-item"/g) || []).length <= 10);
const styleSource = fs.readFileSync(path.join(root, "style.css"), "utf8");
assert.match(styleSource, /\.top-trending-section \.top-trending-list\s*\{[^}]*grid-template-columns:\s*repeat\(2,/s);
assert.match(styleSource, /@media\s*\(max-width:\s*768px\)[\s\S]*?\.top-trending-section \.top-trending-list\s*\{\s*grid-template-columns:\s*minmax\(0,\s*1fr\);/);
assert.match(styleSource, /\.top-trending-section \.top-trending-summary\s*\{[^}]*-webkit-line-clamp:\s*3/s);
console.log(JSON.stringify({ sampleItems: 10, oldData: "supported", unrelatedFiltered: true, emptyEntryFiltered: true, emptySectionHidden: true }));

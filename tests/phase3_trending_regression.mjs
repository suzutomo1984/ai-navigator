import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";


const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const appSource = fs.readFileSync(path.join(root, "app.js"), "utf8");
const indexSource = fs.readFileSync(path.join(root, "index.html"), "utf8");
const data = JSON.parse(fs.readFileSync(path.join(root, "articles.json"), "utf8"));
const context = {
  console,
  document: { addEventListener() {} },
  window: {},
};
vm.createContext(context);
vm.runInContext(
  `${appSource}\n;globalThis.__phase3TestApi = { renderTopTrending, topTrendingSummary };`,
  context,
  { filename: "app.js" },
);

const { renderTopTrending, topTrendingSummary } = context.__phase3TestApi;
const repos = Array.from({ length: 6 }, (_, index) => ({
  title: `owner/repo-${index + 1}`,
  url: `https://github.com/owner/repo-${index + 1}`,
  summary: index === 0 ? "English description only" : "日本語の要約です",
  stars: 100 + index,
  language: "TypeScript",
}));
const html = renderTopTrending(repos);

assert.equal((html.match(/class="top-trending-item"/g) || []).length, 5);
assert.ok(html.includes("owner/repo-1"));
assert.ok(html.includes("★ 100"));
assert.ok(html.includes("要約を準備中です"));
assert.ok(!html.includes("English description only"));
assert.equal(topTrendingSummary({ summary: "English only" }), "要約を準備中です");
assert.equal((indexSource.match(/id=["']top-github-trending["']/g) || []).length, 1);
assert.ok(indexSource.includes("今、作る側が注目しているもの"));
assert.ok(indexSource.includes("GitHub Trending（daily）"));

const actualHtml = renderTopTrending(data.trending || []);
assert.equal((actualHtml.match(/class="top-trending-item"/g) || []).length, 5);
assert.ok(!actualHtml.includes(data.trending[0].githubDescription || "\u0000"));

console.log(JSON.stringify({
  renderedItems: 5,
  actualDataItems: (data.trending || []).slice(0, 5).length,
  fallback: "要約を準備中です",
}));

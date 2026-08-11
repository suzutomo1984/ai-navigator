import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";


const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = name => fs.readFileSync(path.join(root, name), "utf8");
const appSource = read("app.js");
const indexSource = read("index.html");
const newsSource = read("news.html");
const pages = ["index.html", "news.html", "official.html", "about.html"];
const pageRoutes = ["/", "/news", "/official", "/about"];

const contractMatch = appSource.match(/const REQUIRED_DOM_IDS = Object\.freeze\(\[(.*?)\]\);/s);
assert.ok(contractMatch, "REQUIRED_DOM_IDS must exist");
const requiredIds = [...contractMatch[1].matchAll(/"([^"]+)"/g)].map(match => match[1]);
assert.equal(requiredIds.length, 28);
for (const id of requiredIds) {
  const count = (newsSource.match(new RegExp(`id=["']${id}["']`, "g")) || []).length;
  assert.equal(count, 1, `${id} must exist exactly once in news.html`);
}

assert.doesNotMatch(indexSource, /TOP_STATS_GRID|top-number-grid/);
for (const marker of ["TOP_STATS_BAR", "TOP_STATS_COUNT", "TOP_HERO_STATS", "JSON_LD"]) {
  assert.equal((indexSource.match(new RegExp(`<!-- ${marker}:start -->`, "g")) || []).length, 1);
  assert.equal((indexSource.match(new RegExp(`<!-- ${marker}:end -->`, "g")) || []).length, 1);
}
assert.match(indexSource, /href=["']\/news["'][^>]*>今日の全\d+本を見る/);
assert.match(indexSource, /href=["']\/news["'][^>]*>すべて見る →/);
assert.match(appSource, /new URLSearchParams\(window\.location\.search\)\.get\("category"\)/);
assert.match(appSource, /news\.html\?category=\$\{encodeURIComponent\(category\.id\)\}/);

for (const page of pages) {
  const source = read(page);
  const tabbar = source.match(/<nav id="tabbar">(.*?)<\/nav>/s)?.[1] || "";
  const bottomNav = source.match(/<nav id="bottom-nav">(.*?)<\/nav>/s)?.[1] || "";
  const footer = source.match(/<footer\b[^>]*>(.*?)<\/footer>/s)?.[1] || "";
  assert.equal((tabbar.match(/class="tab-btn(?: active)?"/g) || []).length, 4, `${page} tabbar`);
  assert.equal((bottomNav.match(/class="bnav-item(?: active)?"/g) || []).length, 4, `${page} bottom nav`);
  for (const href of pageRoutes) {
    assert.match(footer, new RegExp(`href=["']${href}["']`), `${page} footer must link ${href}`);
  }
}

console.log(JSON.stringify({ requiredDomIds: requiredIds.length, pages: pages.length }));

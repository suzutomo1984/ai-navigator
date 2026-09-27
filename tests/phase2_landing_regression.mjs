import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";


const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const appSource = fs.readFileSync(path.join(root, "app.js"), "utf8");
const indexSource = fs.readFileSync(path.join(root, "index.html"), "utf8");
const styleSource = fs.readFileSync(path.join(root, "style.css"), "utf8");
const data = JSON.parse(fs.readFileSync(path.join(root, "articles.json"), "utf8"));

const context = {
  console,
  document: { addEventListener() {} },
  window: {},
};
vm.createContext(context);
vm.runInContext(
  `${appSource}\n;globalThis.__phase2TestApi = { compareArticlesNewestFirst, getLandingContent, landingThumbnail, topBenefitLabel };`,
  context,
  { filename: "app.js" },
);

const { getLandingContent, landingThumbnail, topBenefitLabel } = context.__phase2TestApi;
const expected = getLandingContent(data.articles, data.categories);

// 入力順を反転しても、トップのリリース・カテゴリ順が変わらないことを保証する。
const shuffled = getLandingContent([...data.articles].reverse(), data.categories);
assert.deepEqual(
  Array.from(shuffled.recentReleases, article => article.id),
  Array.from(expected.recentReleases, article => article.id),
);
assert.deepEqual(
  Array.from(shuffled.topCategories, category => category.id),
  Array.from(expected.topCategories, category => category.id),
);

assert.equal(expected.recentReleases.length, 5);
assert.ok(expected.recentReleases.every(article => article.isOfficial));
// official と other を除く全カテゴリを出す（実データは7種）。
assert.ok(expected.topCategories.length >= 5 && expected.topCategories.length <= 9, `topCategories should be 6-9, got ${expected.topCategories.length}`);
assert.match(landingThumbnail({ thumbnail: "" }, "test-thumb"), /top-thumb-placeholder/);

assert.deepEqual([
  "productivity", "strategy", "sales-marketing", "back-office", "info-mgmt",
  "side-business", "ai-tech", "official", "other",
].map(category => topBenefitLabel({ category })), [
  "【仕事が速くなる】", "【経営の判断材料】", "【売上につながる】", "【事務が楽になる】", "【情報整理に効く】",
  "【個人で稼ぐ】", "【新しい道具】", "【道具の更新】", "【今週の話題】",
]);
assert.equal(topBenefitLabel({ category: "unknown" }), "【今週の話題】");

// Phase 2の静的構造と、Phase 4で追加した統計更新契約。
for (const id of [
  "landing-main",
  "top-new-arrivals",
  "top-new-arrivals-articles",
  "top-category-tiles",
  "top-recent-releases",
  "site-footer",
]) {
  assert.equal((indexSource.match(new RegExp(`id=["']${id}["']`, "g")) || []).length, 1, `${id} must exist exactly once`);
}
assert.equal((indexSource.match(/<footer\b/gi) || []).length, 1);
// TOP_STATS_COUNT はサイト説明バーの記事数。指標バーと同じ実測値を維持する。
for (const marker of ["TOP_STATS_BAR", "TOP_STATS_COUNT", "JSON_LD"]) {
  assert.equal((indexSource.match(new RegExp(`<!-- ${marker}:start -->`, "g")) || []).length, 1);
  assert.equal((indexSource.match(new RegExp(`<!-- ${marker}:end -->`, "g")) || []).length, 1);
}
// 旧トップヒーローとPICK固定枠は、朝刊カードと新着を主役にする新デザインで置き換えた。
assert.match(indexSource, /<section id="top-morning-edition" class="top-morning-edition"/);
const newArrivalsSection = indexSource.match(/<section id="top-new-arrivals"[\s\S]*?<\/section>/)?.[0] || "";
assert.match(newArrivalsSection, /aria-labelledby="new-arrivals-title"[^>]*hidden/);
assert.match(newArrivalsSection, /<h2 id="new-arrivals-title">新着<\/h2>/);
assert.match(newArrivalsSection, /id="top-new-arrivals-meta"/);
assert.match(newArrivalsSection, /id="top-new-arrivals-articles" class="top-pickup"/);
assert.match(newArrivalsSection, /href="\/news">すべて見る →<\/a>/);
assert.doesNotMatch(indexSource, /id=["']top-pickup["']/);
assert.doesNotMatch(indexSource, /id=["']top-latest-news["']/);
const morningAt = indexSource.indexOf('id="top-morning-edition"');
const newArrivalsAt = indexSource.indexOf('id="top-new-arrivals"');
const layoutAt = indexSource.indexOf('class="top-editorial-layout"');
const statsAt = indexSource.indexOf('class="top-stats-bar"');
assert.ok(morningAt < newArrivalsAt && newArrivalsAt < layoutAt && layoutAt < statsAt, "top order must place new arrivals after the morning edition and before the remaining sections");
assert.doesNotMatch(indexSource, /<h2 id="latest-news-title">最新のAIニュース<\/h2>/);
const footer = indexSource.match(/<footer\b[^>]*>(.*?)<\/footer>/s)?.[1] || "";
assert.match(footer, />このサイトの作り方<\/a>/);
assert.match(styleSource, /\.top-morning-edition\s*\{/);
assert.match(styleSource, /\.top-pickup-card\s*\{/);
assert.match(styleSource, /@media \(max-width: 768px\)[\s\S]*?\.top-pickup-card \{[^}]*grid-template-columns: 104px minmax\(0, 1fr\)/);
assert.doesNotMatch(indexSource, /TOP_STATS_GRID/);
assert.doesNotMatch(indexSource, /top-number-grid/);
assert.equal((indexSource.match(/id=["']top-github-trending["']/g) || []).length, 1);

console.log(JSON.stringify({
  recentReleases: expected.recentReleases.map(article => article.id),
  topCategories: expected.topCategories.map(category => category.id),
}, null, 2));

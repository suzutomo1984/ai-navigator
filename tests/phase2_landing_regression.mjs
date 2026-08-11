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

// 入力順を反転しても、3種の記事選択とカテゴリ順が変わらないことを保証する。
const shuffled = getLandingContent([...data.articles].reverse(), data.categories);
assert.deepEqual(
  Array.from(shuffled.pickup, article => article.id),
  Array.from(expected.pickup, article => article.id),
);
assert.deepEqual(
  Array.from(shuffled.latestNews, article => article.id),
  Array.from(expected.latestNews, article => article.id),
);
assert.deepEqual(
  Array.from(shuffled.recentReleases, article => article.id),
  Array.from(expected.recentReleases, article => article.id),
);
assert.deepEqual(
  Array.from(shuffled.topCategories, category => category.id),
  Array.from(expected.topCategories, category => category.id),
);

assert.equal(expected.pickup.length, 4);
assert.equal(expected.latestNews.length, 4);
assert.ok(expected.latestNews.every(article => !article.isOfficial));
assert.equal(expected.recentReleases.length, 5);
assert.ok(expected.recentReleases.every(article => article.isOfficial));
// official と other を除く全カテゴリを出す（実データは7種）。
assert.ok(expected.topCategories.length >= 5 && expected.topCategories.length <= 9, `topCategories should be 6-9, got ${expected.topCategories.length}`);
assert.match(landingThumbnail({ thumbnail: "" }, "test-thumb"), /top-thumb-placeholder/);

// must-readを先頭にし、PICK不足時は重複せず最新記事で4枠を埋める。
const fallbackContent = getLandingContent([
  { id: "latest", date: "2026-08-12", addedAt: "2026-08-12T02:00:00Z" },
  { id: "must", date: "2026-08-11", addedAt: "2026-08-11T02:00:00Z", isPick: true, pickPriority: "must-read" },
  { id: "pick", date: "2026-08-11", addedAt: "2026-08-11T01:00:00Z", isPick: true },
  { id: "older", date: "2026-08-10", addedAt: "2026-08-10T01:00:00Z" },
], []);
assert.deepEqual(Array.from(fallbackContent.pickup, article => article.id), ["must", "pick", "latest", "older"]);

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
  "top-pickup",
  "top-latest-news",
  "top-category-tiles",
  "top-recent-releases",
  "site-footer",
]) {
  assert.equal((indexSource.match(new RegExp(`id=["']${id}["']`, "g")) || []).length, 1, `${id} must exist exactly once`);
}
assert.equal((indexSource.match(/<footer\b/gi) || []).length, 1);
// TOP_STATS_COUNT はサイト説明バーの記事数。指標バーと同じ実測値を維持する。
for (const marker of ["TOP_STATS_BAR", "TOP_STATS_COUNT", "TOP_HERO_STATS", "JSON_LD"]) {
  assert.equal((indexSource.match(new RegExp(`<!-- ${marker}:start -->`, "g")) || []).length, 1);
  assert.equal((indexSource.match(new RegExp(`<!-- ${marker}:end -->`, "g")) || []).length, 1);
}
assert.equal((indexSource.match(/<h1\b/gi) || []).length, 1);
assert.match(indexSource, /<h1 id=["']top-hero-title["']>AIと共に、<br>ビジネスの未来をナビゲート。<\/h1>/);
assert.match(indexSource, /<p class=["']top-eyebrow["']>AI BUSINESS NEWS \/ UPDATED TWICE DAILY<\/p>/);
const heroSection = indexSource.match(/<section class="top-hero"[\s\S]*?<\/section>/)?.[0] || "";
assert.match(heroSection, /class="top-hero-orbit"/);
assert.match(heroSection, /href="\/news"[^>]*>最新のAIニュースを読む<\/a>/);
assert.match(heroSection, /href="\/about"[^>]*>このサイトの作り方<\/a>/);
assert.equal((heroSection.match(/class="top-action /g) || []).length, 2);
const heroAt = indexSource.indexOf('class="top-hero"');
const pickAt = indexSource.indexOf('class="top-section top-pick-section"');
const layoutAt = indexSource.indexOf('class="top-editorial-layout"');
const statsAt = indexSource.indexOf('class="top-stats-bar"');
assert.ok(heroAt < pickAt && pickAt < layoutAt && layoutAt < statsAt, "top order must be hero -> PICK -> layout -> stats");
const heroStatsAt = indexSource.indexOf("<!-- TOP_HERO_STATS:start -->");
assert.ok(heroStatsAt > indexSource.indexOf('id="top-pickup"') && heroStatsAt < layoutAt, "TOP_HERO_STATS must be directly below PICK");
const footer = indexSource.match(/<footer\b[^>]*>(.*?)<\/footer>/s)?.[1] || "";
assert.match(footer, />このサイトの作り方<\/a>/);
assert.match(styleSource, /\.top-hero\s*\{[^}]*min-height:\s*540px;[^}]*padding:\s*92px 24px 84px;/s);
assert.match(styleSource, /@media \(max-width: 768px\)[\s\S]*?\.top-hero\s*\{[^}]*min-height:\s*510px;[^}]*padding:\s*72px 20px 70px;/);
assert.equal((styleSource.match(/hero-compass\.webp/g) || []).length, 2);
assert.match(styleSource, /\.top-hero::before[\s\S]*?\.top-hero::after/);
assert.match(styleSource, /\.top-hero-orbit\s*\{/);
assert.match(styleSource, /\.top-editorial-layout\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1fr\) 310px;/s);
assert.doesNotMatch(indexSource, /TOP_STATS_GRID/);
assert.doesNotMatch(indexSource, /top-number-grid/);
assert.equal((indexSource.match(/id=["']top-github-trending["']/g) || []).length, 1);

console.log(JSON.stringify({
  pickup: expected.pickup.map(article => article.id),
  latestNews: expected.latestNews.map(article => article.id),
  recentReleases: expected.recentReleases.map(article => article.id),
  topCategories: expected.topCategories.map(category => category.id),
}, null, 2));

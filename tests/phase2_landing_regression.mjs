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
  `${appSource}\n;globalThis.__phase2TestApi = { compareArticlesNewestFirst, getLandingContent, landingThumbnail };`,
  context,
  { filename: "app.js" },
);

const { getLandingContent, landingThumbnail } = context.__phase2TestApi;
const expected = getLandingContent(data.articles, data.categories);

// 入力順を反転しても、3種の記事選択とカテゴリ順が変わらないことを保証する。
const shuffled = getLandingContent([...data.articles].reverse(), data.categories);
assert.equal(shuffled.pickup.id, expected.pickup.id);
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

assert.equal(expected.latestNews.length, 4);
assert.ok(expected.latestNews.every(article => !article.isOfficial));
assert.equal(expected.recentReleases.length, 5);
assert.ok(expected.recentReleases.every(article => article.isOfficial));
assert.equal(expected.topCategories.length, 6);
assert.match(landingThumbnail({ thumbnail: "" }, "test-thumb"), /top-thumb-placeholder/);

// Phase 2の静的構造と、Phase 4で追加した統計更新契約。
for (const id of [
  "landing-main",
  "top-pickup",
  "top-latest-news",
  "top-category-tiles",
  "top-recent-releases",
  "article-list-start",
  "site-footer",
]) {
  assert.equal((indexSource.match(new RegExp(`id=["']${id}["']`, "g")) || []).length, 1, `${id} must exist exactly once`);
}
assert.equal((indexSource.match(/<footer\b/gi) || []).length, 1);
for (const marker of ["TOP_STATS_BAR", "TOP_STATS_GRID"]) {
  assert.equal((indexSource.match(new RegExp(`<!-- ${marker}:start -->`, "g")) || []).length, 1);
  assert.equal((indexSource.match(new RegExp(`<!-- ${marker}:end -->`, "g")) || []).length, 1);
}
assert.equal((indexSource.match(/id=["']top-github-trending["']/g) || []).length, 1);

console.log(JSON.stringify({
  pickup: expected.pickup.id,
  latestNews: expected.latestNews.map(article => article.id),
  recentReleases: expected.recentReleases.map(article => article.id),
  topCategories: expected.topCategories.map(category => category.id),
}, null, 2));

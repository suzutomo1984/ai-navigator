import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";


const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const appSource = fs.readFileSync(path.join(root, "app.js"), "utf8");
const data = JSON.parse(fs.readFileSync(path.join(root, "articles.json"), "utf8"));


function createContext({ captureDomReady = false } = {}) {
  let domReady = null;
  const warnings = [];
  const errors = [];
  const document = {
    addEventListener(type, callback) {
      if (captureDomReady && type === "DOMContentLoaded") domReady = callback;
    },
    getElementById() {
      return null;
    },
    querySelectorAll() {
      return [];
    },
    body: { style: {} },
    documentElement: { style: {} },
  };
  const context = {
    clearTimeout,
    console: {
      error: (...args) => errors.push(args),
      warn: (...args) => warnings.push(args),
    },
    document,
    fetch: async () => ({ json: async () => ({ articles: [], dates: [], categories: [] }) }),
    setTimeout,
    window: { innerWidth: 1024, scrollTo() {} },
  };
  vm.createContext(context);
  vm.runInContext(
    `${appSource}\n;globalThis.__phase1TestApi = { state, filterArticles, isValidArticle, setArticles(value) { allArticles = value; } };`,
    context,
    { filename: "app.js" },
  );
  return { context, domReady: () => domReady, errors, warnings };
}


function testRealDataFilters() {
  const { context } = createContext();
  const api = context.__phase1TestApi;
  const validArticles = data.articles.filter(article => api.isValidArticle(article));
  api.setArticles(validArticles);

  Object.assign(api.state, { tab: "latest", category: "all", date: "all", search: "", page: 1 });
  const baseline = api.filterArticles();
  assert.ok(baseline.length > 0, "latest article baseline must not be empty");

  const searchCandidate = baseline.find(article => article.title && article.title.length >= 10);
  assert.ok(searchCandidate, "search fixture article must exist");
  api.state.search = searchCandidate.title;
  const searchResults = api.filterArticles();
  assert.ok(searchResults.length > 0 && searchResults.length < baseline.length);

  api.state.search = "";
  const categoryCandidate = baseline.find(article => article.category)?.category;
  assert.ok(categoryCandidate, "category fixture must exist");
  api.state.category = categoryCandidate;
  const categoryResults = api.filterArticles();
  assert.ok(categoryResults.length > 0);
  assert.ok(categoryResults.every(article => article.category === categoryCandidate));

  api.state.category = "all";
  const dateCandidate = baseline.find(article => article.date)?.date;
  assert.ok(dateCandidate, "date fixture must exist");
  api.state.date = dateCandidate;
  const dateResults = api.filterArticles();
  assert.ok(dateResults.length > 0);
  assert.ok(dateResults.every(article => article.date === dateCandidate));

  return {
    rawArticles: data.articles.length,
    validArticles: validArticles.length,
    latestBaseline: baseline.length,
    searchResults: searchResults.length,
    category: categoryCandidate,
    categoryResults: categoryResults.length,
    date: dateCandidate,
    dateResults: dateResults.length,
  };
}


async function testMissingDomDoesNotStopInitialization() {
  const harness = createContext({ captureDomReady: true });
  const callback = harness.domReady();
  assert.equal(typeof callback, "function");
  callback();
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(harness.errors.length, 0, "missing DOM must not produce console errors");
  assert.ok(
    harness.warnings.some(args => String(args[0]).includes("#modal-close-btn")),
    "missing required DOM must produce a warning",
  );
  return { warnings: harness.warnings.length, errors: harness.errors.length };
}


const filterEvidence = testRealDataFilters();
const guardEvidence = await testMissingDomDoesNotStopInitialization();
console.log(JSON.stringify({ filterEvidence, guardEvidence }, null, 2));

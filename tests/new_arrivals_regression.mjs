import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const appSource = fs.readFileSync(path.join(root, "app.js"), "utf8");
const savedEditions = JSON.parse(fs.readFileSync(path.join(root, "daily", "editions.json"), "utf8"));
const context = { console, document: { addEventListener() {} }, window: {} };
vm.createContext(context);
vm.runInContext(
  appSource + "\nglobalThis.__newArrivalsTestApi = { getLatestEdition, getNewArrivalsContent };",
  context,
  { filename: "app.js" },
);
const { getLatestEdition, getNewArrivalsContent } = context.__newArrivalsTestApi;

const editions = [
  { date: "2026-09-26", edition: "pm", batchAt: "2026-09-26T21:00:00+09:00", selectedIds: ["yesterday-story"] },
  { date: "2026-09-27", edition: "am", batchAt: "2026-09-27T08:11:57.265084+09:00", selectedIds: ["morning-story"] },
];
const articles = [
  { id: "morning-story", date: "2026-09-27", addedAt: "2026-09-27T08:10:00+09:00", url: "https://example.com/morning-story" },
  { id: "latest", date: "2026-09-27", addedAt: "2026-09-27T21:32:08.282948+09:00", url: "https://example.com/latest" },
  { id: "same-date-older", date: "2026-09-27", addedAt: "2026-09-27T21:31:00+09:00", url: "https://example.com/same-date-older" },
  { id: "same-time-new-date", date: "2026-09-28", addedAt: "2026-09-27T21:31:00+09:00", url: "https://example.com/same-time-new-date" },
  { id: "after-4", date: "2026-09-27", addedAt: "2026-09-27T21:30:00+09:00", url: "https://example.com/after-4" },
  { id: "after-5", date: "2026-09-27", addedAt: "2026-09-27T21:29:00+09:00", url: "https://example.com/after-5" },
  { id: "after-6", date: "2026-09-27", addedAt: "2026-09-27T21:28:00+09:00", url: "https://example.com/after-6" },
  { id: "after-7", date: "2026-09-27", addedAt: "2026-09-27T21:27:00+09:00", url: "https://example.com/after-7" },
  { id: "after-8", date: "2026-09-27", addedAt: "2026-09-27T21:26:00+09:00", url: "https://example.com/after-8" },
  { id: "no-url", date: "2026-09-27", addedAt: "2026-09-27T21:25:00+09:00", url: "" },
  { id: "bad-url", date: "2026-09-27", addedAt: "2026-09-27T21:24:00+09:00", url: "invalid" },
  { id: "official", date: "2026-09-27", addedAt: "2026-09-27T21:23:00+09:00", url: "https://example.com/official", isOfficial: true },
  { id: "no-added-at", date: "2026-09-27", url: "https://example.com/no-added-at" },
];

assert.equal(getLatestEdition(editions).date, "2026-09-27");
const savedLatestIssue = getLatestEdition(savedEditions);
assert.ok(Array.isArray(savedLatestIssue.selectedIds) && savedLatestIssue.selectedIds.length > 0, "the saved 2026-09-27 issue must expose its article IDs");
assert.equal(savedLatestIssue.selectedIds.length, savedLatestIssue.selectedCount);
const night = getNewArrivalsContent(articles, editions);
assert.ok(!Array.from(night.items, article => article.id).includes("morning-story"), "articles in the latest issue must be excluded by ID");
assert.equal(night.afterBatchCount, 8);
assert.equal(night.description, "朝刊のあと、9月27日 21:32 の配信で8本");
assert.equal(night.totalCount, 9);
assert.deepEqual(Array.from(night.items, article => article.id), [
  "latest", "same-time-new-date", "same-date-older", "after-4", "after-5", "after-6",
]);

const morning = getNewArrivalsContent([
  { id: "unpicked-morning", date: "2026-09-27", addedAt: "2026-09-27T08:10:00+09:00", url: "https://example.com/unpicked-morning" },
], editions);
assert.equal(morning.description, "朝刊に載らなかった今朝の新着");
assert.equal(morning.items[0].id, "unpicked-morning");

const noEditions = getNewArrivalsContent(articles, undefined);
assert.equal(noEditions.description, "最新のAIニュース");
assert.equal(noEditions.totalCount, 10);
assert.equal(getNewArrivalsContent([articles[0]], undefined).items[0].id, "morning-story", "without editions there is no ID exclusion");

assert.equal(getLatestEdition(undefined), null);
assert.equal(getNewArrivalsContent([
  { id: "only-in-issue", date: "2026-09-27", addedAt: "2026-09-27T09:00:00+09:00", url: "https://example.com/only-in-issue" },
], [{ date: "2026-09-27", edition: "am", selectedIds: ["only-in-issue"] }]), null, "zero eligible articles hide the section");

console.log("New arrivals section regression: OK");

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const appSource = fs.readFileSync(path.join(root, "app.js"), "utf8");
const context = { console, document: { addEventListener() {} }, window: {} };
vm.createContext(context);
vm.runInContext(
  appSource + "\nglobalThis.__afterEditionTestApi = { getLatestEditionBatch, getAfterEditionContent, formatAfterEditionMeta };",
  context,
  { filename: "app.js" },
);
const { getLatestEditionBatch, getAfterEditionContent, formatAfterEditionMeta } = context.__afterEditionTestApi;

const editions = [
  { date: "2026-09-26", edition: "pm", batchAt: "2026-09-26T21:00:00+09:00" },
  { date: "2026-09-27", edition: "am", batchAt: "2026-09-27T08:11:57.265084+09:00" },
];
const articles = [
  { id: "old", date: "2026-09-27", addedAt: "2026-09-27T08:11:56.999+09:00", url: "https://example.com/old" },
  { id: "at-batch", date: "2026-09-27", addedAt: "2026-09-27T08:11:57.265+09:00", url: "https://example.com/at-batch" },
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

assert.equal(getLatestEditionBatch(editions).date, "2026-09-27");
const content = getAfterEditionContent(articles, editions);
assert.equal(content.totalCount, 8, "count includes all qualifying articles, not only the six rendered cards");
assert.equal(content.items.length, 6, "rendering is capped at six");
assert.deepEqual(Array.from(content.items, article => article.id), [
  "latest", "same-time-new-date", "same-date-older", "after-4", "after-5", "after-6",
]);
assert.equal(content.latestAddedAt, "2026-09-27T21:32:08.282948+09:00");
assert.equal(formatAfterEditionMeta(content.latestAddedAt, content.totalCount), "9月27日 21:32 の配信で8本");

assert.equal(getLatestEditionBatch(undefined), null);
assert.equal(getLatestEditionBatch([{ date: "2026-09-27", edition: "am" }]), null);
assert.equal(getAfterEditionContent(articles, undefined), null, "the section has no content when editions.json is unavailable");
assert.equal(getAfterEditionContent(articles, [{ date: "2026-09-27", edition: "am", batchAt: "2026-09-27T22:00:00+09:00" }]), null, "the section has no content when no articles arrived after the issue");

console.log("After-edition section regression: OK");

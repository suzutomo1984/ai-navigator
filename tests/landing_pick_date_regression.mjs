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
  `${appSource}\n;globalThis.__pickTestApi = { getLandingContent, pickupHeading };`,
  context,
  { filename: "app.js" },
);
const { getLandingContent, pickupHeading } = context.__pickTestApi;

const articles = [
  { id: "yesterday-must", date: "2026-09-26", addedAt: "2026-09-26T02:00:00Z", isPick: true, pickPriority: "must-read" },
  { id: "today-filler", date: "2026-09-27", addedAt: "2026-09-27T03:00:00Z" },
  { id: "today-worth", date: "2026-09-27", addedAt: "2026-09-27T02:00:00Z", isPick: true, pickPriority: "worth-checking" },
  { id: "today-must-1", date: "2026-09-27", addedAt: "2026-09-27T01:00:00Z", isPick: true, pickPriority: "must-read" },
  { id: "today-must-2", date: "2026-09-27", addedAt: "2026-09-27T00:00:00Z", isPick: true, pickPriority: "must-read" },
];

// 旧処理の順序では、今日のmust-readが2本だと3本目に前日のmust-readが入る。
const newest = items => [...items].sort((a, b) =>
  String(b.date || "").localeCompare(String(a.date || "")) ||
  String(b.addedAt || "").localeCompare(String(a.addedAt || "")) ||
  String(a.id || "").localeCompare(String(b.id || "")));
const oldSelection = [
  ...newest(articles.filter(article => article.pickPriority === "must-read")),
  ...newest(articles.filter(article => article.isPick && article.pickPriority !== "must-read")),
];
assert.equal(oldSelection[2].id, "yesterday-must", "the regression fixture must reproduce the old previous-day leak");

const fixed = getLandingContent(articles, []).pickup;
assert.deepEqual(Array.from(fixed, article => article.id), [
  "today-must-1", "today-must-2", "today-worth", "today-filler",
]);
assert.ok(Array.from(fixed, article => article.date).every(date => date === "2026-09-27"));
assert.equal(pickupHeading("2026-09-28", "2026-09-28"), "今日の重要4本");
assert.equal(pickupHeading("2026-09-27", "2026-09-28"), "9月27日の重要4本");

const short = getLandingContent([
  { id: "only-must", date: "2026-09-27", addedAt: "2026-09-27T02:00:00Z", isPick: true, pickPriority: "must-read" },
  { id: "only-extra", date: "2026-09-27", addedAt: "2026-09-27T01:00:00Z" },
  { id: "older-extra", date: "2026-09-26", addedAt: "2026-09-26T01:00:00Z" },
], []).pickup;
assert.deepEqual(Array.from(short, article => article.id), ["only-must", "only-extra"]);

console.log("Landing PICK latest-date regression: OK");

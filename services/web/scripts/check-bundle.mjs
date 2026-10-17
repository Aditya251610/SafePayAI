// Fails the build when any route's first-load JavaScript is over the budget.
// Run after `next build`. Sizes are gzip, summed over each route's chunks
// from the app build manifest (shared chunks counted once per route).
import { readFileSync } from "node:fs";
import { gzipSync } from "node:zlib";
import path from "node:path";

const BUDGET_KB = Number(process.env.BUNDLE_BUDGET_KB ?? 180);
const dir = path.resolve(import.meta.dirname, "../.next");
const manifest = JSON.parse(readFileSync(path.join(dir, "app-build-manifest.json"), "utf8"));

const cache = new Map();
function gz(file) {
  if (!cache.has(file)) cache.set(file, gzipSync(readFileSync(path.join(dir, file))).length);
  return cache.get(file);
}

const rows = Object.entries(manifest.pages)
  .map(([route, files]) => ({
    route,
    kb: files.filter((f) => f.endsWith(".js")).reduce((n, f) => n + gz(f), 0) / 1024,
  }))
  .sort((a, b) => b.kb - a.kb);

for (const r of rows) console.log(`${r.kb.toFixed(1).padStart(7)} KB  ${r.route}`);

const over = rows.filter((r) => r.kb > BUDGET_KB);
if (over.length > 0) {
  console.error(`\nOver the ${BUDGET_KB} KB budget: ${over.map((r) => r.route).join(", ")}`);
  process.exit(1);
}
console.log(`\nAll ${rows.length} routes are within ${BUDGET_KB} KB.`);

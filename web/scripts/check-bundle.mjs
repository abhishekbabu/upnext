/**
 * Fail the build when the entry bundle grows past what this app can justify.
 *
 * Everything here is loaded before anything renders, so its size is time the
 * page is blank. A budget catches the case a dependency is added for one small
 * thing and brings a library with it — invisible in review, and months later
 * "the app got slow".
 *
 * Raise BUDGET deliberately, with the reason in the commit.
 */
import { gzipSync } from "node:zlib";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const DIST = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../dist/assets");
// 105, measured at 98 for React + react-router + react-query. That trio is the
// whole runtime — every page routes, and every panel reads the API through a
// cache — so it belongs in the entry bundle. The 7 kB of headroom is for a
// component or two, not for another library.
const BUDGET_KB = 105;

const files = await readdir(DIST);
const entry = files.find((f) => f.startsWith("index-") && f.endsWith(".js"));
if (!entry) {
  console.error("  No entry bundle found. Did the build run?");
  process.exit(1);
}

const gzipped = gzipSync(await readFile(path.join(DIST, entry))).length / 1024;
console.log(`  entry ${gzipped.toFixed(1)} kB gzip (budget ${BUDGET_KB})`);

if (gzipped > BUDGET_KB) {
  console.error(`\n  Over budget by ${(gzipped - BUDGET_KB).toFixed(1)} kB.`);
  console.error("  Either defer it behind a dynamic import, or raise BUDGET with the reason.");
  process.exit(1);
}

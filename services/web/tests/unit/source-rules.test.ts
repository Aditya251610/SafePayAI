import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { BANNED_PHRASES, findBanned } from "@/lib/honesty/banned";

const ROOT = path.resolve(__dirname, "../..");

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name === ".next") continue;
    const p = path.join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.(ts|tsx|css)$/.test(name)) out.push(p);
  }
  return out;
}

const appFiles = ["app", "components", "lib"].flatMap((d) => walk(path.join(ROOT, d)));
const rel = (p: string) => path.relative(ROOT, p);

describe("source rules", () => {
  it("scans a non-trivial number of files", () => {
    expect(appFiles.length).toBeGreaterThan(10);
  });

  it("contains no banned claims in app source", () => {
    const hits = appFiles
      .filter((p) => !p.endsWith("honesty/banned.ts"))
      .flatMap((p) => findBanned(readFileSync(p, "utf8")).map((w) => `${rel(p)}: ${w}`));
    expect(hits).toEqual([]);
  });

  it("detects banned phrases case-insensitively", () => {
    expect(findBanned("This is Fraud-Proof")).toEqual(["fraud-proof"]);
    expect(findBanned("Sandbox only")).toEqual([]);
    expect(BANNED_PHRASES.length).toBeGreaterThanOrEqual(10);
  });

  it("calls fetch only inside lib/api", () => {
    const hits = appFiles
      .filter((p) => !rel(p).startsWith(path.join("lib", "api")))
      .filter((p) => /(^|[^.\w])fetch\s*\(/.test(readFileSync(p, "utf8")))
      .map(rel);
    expect(hits).toEqual([]);
  });

  it("never hard-codes an API base outside lib/api/config.ts", () => {
    const hits = appFiles
      .filter((p) => rel(p) !== path.join("lib", "api", "config.ts"))
      .filter((p) => /["'`]\/api["'`\/]/.test(readFileSync(p, "utf8")))
      .map(rel);
    expect(hits).toEqual([]);
  });

  it("does no arithmetic on *_minor values", () => {
    const re = /\b\w*_minor\b\s*[-+*/%]\s*[\w(]|[\w)]\s*[-+*/%]\s*\w*_minor\b/;
    const hits = appFiles
      .filter((p) => /\.(ts|tsx)$/.test(p))
      .filter((p) =>
        readFileSync(p, "utf8")
          .split("\n")
          .some((l) => !l.trim().startsWith("//") && !l.trim().startsWith("*") && re.test(l)),
      )
      .map(rel);
    expect(hits).toEqual([]);
  });
});

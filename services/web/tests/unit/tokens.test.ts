import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

const ROOT = path.resolve(__dirname, "../..");
const css = readFileSync(path.join(ROOT, "styles/tokens.css"), "utf8");

function block(startMarker: string): string {
  const start = css.indexOf(startMarker);
  expect(start).toBeGreaterThan(-1);
  const open = css.indexOf("{", start);
  let depth = 0;
  for (let i = open; i < css.length; i += 1) {
    if (css[i] === "{") depth += 1;
    if (css[i] === "}") {
      depth -= 1;
      if (depth === 0) return css.slice(open, i + 1);
    }
  }
  throw new Error("unbalanced css");
}

const names = (b: string) => Array.from(b.matchAll(/(--[\w-]+)\s*:/g)).map((m) => m[1] as string);

describe("design tokens", () => {
  const base = block(":root {");
  const osLight = block("@media (prefers-color-scheme: light)");
  const forcedLight = block(':root[data-theme="light"]');
  const themed = names(base).filter((n) => n !== "--slab");

  it("define the light palette for the OS preference and for the toggle", () => {
    for (const n of themed) {
      expect(names(osLight), `os light is missing ${n}`).toContain(n);
      expect(names(forcedLight), `forced light is missing ${n}`).toContain(n);
    }
  });

  it("use identical light values in both light blocks", () => {
    for (const n of themed) {
      const re = new RegExp(`${n}:\\s*([^;]+);`);
      expect(osLight.match(re)?.[1]).toBe(forcedLight.match(re)?.[1]);
    }
  });

  it("keep the OS light block from overriding an explicit dark choice", () => {
    expect(css).toContain(':root:not([data-theme="dark"])');
  });

  it("is the only place a hex colour appears", () => {
    function walk(dir: string, out: string[] = []): string[] {
      for (const name of readdirSync(dir)) {
        if (name === "node_modules" || name === ".next") continue;
        const p = path.join(dir, name);
        if (statSync(p).isDirectory()) walk(p, out);
        else if (/\.(ts|tsx|css)$/.test(name)) out.push(p);
      }
      return out;
    }
    const files = ["app", "components", "lib", "styles"]
      .flatMap((d) => walk(path.join(ROOT, d)))
      .filter((p) => !p.endsWith(path.join("styles", "tokens.css")));
    const hits = files.filter((p) => /#[0-9a-fA-F]{3,8}\b/.test(readFileSync(p, "utf8")));
    expect(hits.map((p) => path.relative(ROOT, p))).toEqual([]);
  });
});

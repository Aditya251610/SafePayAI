import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Vitest config for component/unit smoke tests (ci-cd-and-repo-workflow.md
// web CI job list: eslint, tsc --noEmit, vitest, next build). Playwright
// owns e2e/a11y (tests/e2e/**), excluded here.

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/unit/setup.ts"],
    include: ["tests/unit/**/*.test.{ts,tsx}"],
    exclude: ["tests/e2e/**", "node_modules/**"],
    coverage: {
      provider: "v8",
      include: ["lib/**/*.ts"],
      exclude: ["lib/utils.ts", "lib/api/schemas/**"],
      thresholds: { lines: 90, functions: 90, statements: 90, branches: 80 },
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
});

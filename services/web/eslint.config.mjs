import { FlatCompat } from "@eslint/eslintrc";

// ESLint flat config. Two project-specific rules enforce honesty/safety
// requirements from prd.md:
//   - REQ-WB-006: dangerouslySetInnerHTML is banned everywhere (all server/AI/
//     buyer/catalog text renders as plain text only).
//   - REQ-WB-004: banned-claims words must not appear in source copy
//     ("PayPal-backed" etc, spec.md sec 5). The literal word list lives in
//     tests/unit/banned-words.ts (Wave 5) and is enforced there as a source
//     lint test plus a runtime crawl test, per test-plan.md sec 1 - this file
//     only wires the dangerouslySetInnerHTML ESLint rule, since a generic
//     banned-word check is a text-scan test, not an ESLint rule.

const compat = new FlatCompat({ baseDirectory: import.meta.dirname });

const eslintConfig = [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    rules: {
      "react/no-danger": "error",
      // lib/api-client.ts's Wave 4 stub functions intentionally take
      // unused, underscore-prefixed params (documenting the real shape a
      // Wave 5 implementation will fill in) - don't warn on those.
      "@typescript-eslint/no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],
    },
  },
  {
    // Every network call goes through lib/api so CSRF, idempotency keys and
    // error normalisation cannot be skipped.
    files: ["app/**/*.{ts,tsx}", "components/**/*.{ts,tsx}", "lib/**/*.{ts,tsx}"],
    ignores: ["lib/api/**"],
    rules: {
      "no-restricted-globals": [
        "error",
        { name: "fetch", message: "Use the typed client in lib/api instead of fetch." },
        { name: "XMLHttpRequest", message: "Use the typed client in lib/api." },
      ],
      "no-restricted-properties": [
        "error",
        { object: "window", property: "fetch", message: "Use the typed client in lib/api." },
        { object: "globalThis", property: "fetch", message: "Use the typed client in lib/api." },
      ],
    },
  },
  {
    // Money is computed by the server only. Display code formats integers and
    // never does arithmetic on *_minor values.
    files: ["app/**/*.{ts,tsx}", "components/**/*.{ts,tsx}", "lib/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector:
            "BinaryExpression[operator=/^[-+*\\/%]$/] > MemberExpression[property.name=/_minor$/]",
          message: "No arithmetic on *_minor values; the server computes money.",
        },
        {
          selector: "BinaryExpression[operator=/^[-+*\\/%]$/] > Identifier[name=/_minor$/]",
          message: "No arithmetic on *_minor values; the server computes money.",
        },
      ],
    },
  },
  {
    ignores: [
      ".next/**",
      "node_modules/**",
      "playwright-report/**",
      "test-results/**",
      "next-env.d.ts",
    ],
  },
];

export default eslintConfig;

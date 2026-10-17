import { FlatCompat } from "@eslint/eslintrc";

// ESLint flat config. Project rules beyond the Next defaults:
//   - dangerouslySetInnerHTML is banned: all server, AI, buyer and catalog text
//     renders as plain text.
//   - raw fetch is banned outside lib/api, and arithmetic on *_minor values is
//     banned everywhere (see the blocks below).
// The banned-claims word list is enforced by tests/unit/source-rules.test.ts.

const compat = new FlatCompat({ baseDirectory: import.meta.dirname });

const eslintConfig = [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    rules: {
      "react/no-danger": "error",
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

// @ts-check
/**
 * Lint rules are the enforceable half of AGENTS.md. When a rule fires, fix the
 * code — do not disable the rule. A justified exception needs an
 * `eslint-disable-next-line <rule> -- <reason>` comment (the reason is required).
 */
import eslintComments from "@eslint-community/eslint-plugin-eslint-comments/configs";
import tanstackQuery from "@tanstack/eslint-plugin-query";
import vitest from "@vitest/eslint-plugin";
import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import prettierConfig from "eslint-config-prettier";
import betterTailwindcss from "eslint-plugin-better-tailwindcss";
import { getDefaultSelectors } from "eslint-plugin-better-tailwindcss/defaults";
import jsxA11y from "eslint-plugin-jsx-a11y";
import storybook from "eslint-plugin-storybook";
import testingLibrary from "eslint-plugin-testing-library";
import globals from "globals";

import local from "./eslint-rules/index.mjs";

const TS_FILES = ["**/*.{ts,tsx,mts}"];
const SRC_FILES = ["src/**/*.{ts,tsx}"];
const TEST_FILES = ["**/*.test.{ts,tsx}", "src/test/**/*.{ts,tsx}"];
const STORY_FILES = ["**/*.stories.{ts,tsx}"];

/* ── Design system: only token classes ─────────────────────────────────────── */

const ANY_VARIANTS = "^(?:\\S*:)?";
const ARBITRARY = "(?:\\[.+\\]|\\(.+\\))";

const RESTRICTED_CLASSES = [
  {
    pattern: `${ANY_VARIANTS}(?:bg|text|border(?:-[xytrblse])?|ring|ring-offset|outline|fill|stroke|shadow|divide|from|via|to|caret|accent|decoration|placeholder)-${ARBITRARY}$`,
    message:
      "Arbitrary colours and sizes bypass the design system. Use a token class from src/styles/tokens.css.",
  },
  {
    pattern: `${ANY_VARIANTS}rounded(?:-[trblse]{1,2})?-${ARBITRARY}$`,
    message: "Use the radius scale: rounded-xs … rounded-3xl.",
  },
  {
    pattern: `${ANY_VARIANTS}(?:font|tracking|leading)-${ARBITRARY}$`,
    message: "Use the type tokens: font-medium, tracking-tight, leading-snug.",
  },
  {
    pattern: `${ANY_VARIANTS}-?z-(?:\\d+|${ARBITRARY})$`,
    message:
      "Use a stacking layer: layer-sticky, layer-header, layer-overlay, layer-modal, layer-popover, layer-toast, layer-tooltip.",
  },
  {
    pattern: `${ANY_VARIANTS}duration-(?:\\d+|${ARBITRARY})$`,
    message:
      "Use a named duration: duration-instant, duration-press, duration-fast, duration-base, duration-slow.",
  },
  {
    pattern: `${ANY_VARIANTS}(?:ease|animate|blur|backdrop-blur)-${ARBITRARY}$`,
    message: "Use the motion tokens (ease-out, ease-in-out, ease-drawer) and defined animations.",
  },
  {
    pattern: `${ANY_VARIANTS}-?(?:p|px|py|pt|pr|pb|pl|ps|pe|m|mx|my|mt|mr|mb|ml|ms|me|gap|gap-x|gap-y|space-x|space-y)-${ARBITRARY}$`,
    message: "Use the 4px spacing scale (p-3, gap-2 …) instead of arbitrary spacing.",
  },
  {
    pattern: "(?:^!|!$)",
    message: "Important modifiers hide cascade problems. Fix the specificity instead.",
  },
];

/* ── Architecture: who may import whom ─────────────────────────────────────── */

const RESTRICTED_PATHS = [
  {
    name: "@hugeicons/react",
    message: "Render icons with <Icon icon={…} /> from @/components/ui/icon.",
  },
  { name: "framer-motion", message: 'Import Motion from "motion/react".' },
  { name: "next-themes", message: "Use useTheme from @/lib/theme/use-theme." },
  { name: "lucide-react", message: "The icon set is Hugeicons: <Icon icon={…} />." },
  { name: "clsx", message: "Use cn() from @/lib/utils." },
  { name: "tailwind-merge", message: "Use cn() from @/lib/utils." },
  { name: "zod/v3", message: 'Use Zod 4: import { z } from "zod".' },
  { name: "next/router", message: "App Router only: use next/navigation." },
  {
    name: "@tanstack/react-table",
    importNames: ["useLegacyTable"],
    message: "Use DataTable (TanStack Table v9).",
  },
];

const PARENT_IMPORT = {
  group: ["../*", "../**"],
  message: "Import from outside this folder through the @/ alias.",
};

/**
 * @param {string[]} files
 * @param {string[]} blocked
 * @param {string} message
 * @param {{ allow?: string[], ignores?: string[] }} [options]
 */
function boundary(files, blocked, message, options = {}) {
  const { allow = [], ignores = [] } = options;
  return {
    files,
    ignores,
    rules: {
      "no-restricted-imports": [
        "error",
        {
          paths: RESTRICTED_PATHS.filter((entry) => !allow.includes(entry.name)),
          patterns:
            blocked.length > 0 ? [PARENT_IMPORT, { group: blocked, message }] : [PARENT_IMPORT],
        },
      ],
    },
  };
}

const FC_SYNTAX = {
  selector: "TSQualifiedName[right.name='FC']",
  message: "Use a function declaration with typed props and an explicit return type.",
};
const FORMAT_SYNTAX = [
  {
    selector: "NewExpression[callee.object.name='Intl']",
    message: "Format numbers, money and dates through @/lib/format.",
  },
  {
    selector: "CallExpression[callee.property.name=/^toLocale(Date|Time)?String$/]",
    message: "Format numbers, money and dates through @/lib/format.",
  },
];
const DEFAULT_EXPORT_SYNTAX = {
  selector: "ExportDefaultDeclaration",
  message:
    "Use named exports. Default exports are only for Next.js route files, configs and stories.",
};

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  ...tanstackQuery.configs["flat/recommended"],
  ...storybook.configs["flat/recommended"],
  eslintComments.recommended,

  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "coverage/**",
    "storybook-static/**",
    "playwright-report/**",
    "test-results/**",
    "next-env.d.ts",
    "public/mockServiceWorker.js",
    "Docs/**",
  ]),

  {
    settings: {
      "import/resolver": { typescript: { alwaysTryTypes: true, project: "./tsconfig.json" } },
    },
    rules: {
      "@eslint-community/eslint-comments/require-description": "error",
      "@eslint-community/eslint-comments/disable-enable-pair": ["error", { allowWholeFile: true }],
      "@eslint-community/eslint-comments/no-unlimited-disable": "error",
      "@eslint-community/eslint-comments/no-unused-disable": "error",
    },
  },

  /* TypeScript — strict, typed */
  {
    files: TS_FILES,
    languageOptions: {
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    rules: {
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/consistent-type-assertions": ["error", { assertionStyle: "never" }],
      "@typescript-eslint/consistent-type-imports": [
        "error",
        { prefer: "type-imports", fixStyle: "inline-type-imports" },
      ],
      "@typescript-eslint/no-import-type-side-effects": "error",
      "@typescript-eslint/no-floating-promises": "error",
      "@typescript-eslint/no-misused-promises": [
        "error",
        { checksVoidReturn: { attributes: false } },
      ],
      "@typescript-eslint/await-thenable": "error",
      "@typescript-eslint/switch-exhaustiveness-check": [
        "error",
        { considerDefaultExhaustiveForUnions: true },
      ],
      "@typescript-eslint/explicit-function-return-type": [
        "error",
        {
          allowExpressions: true,
          allowTypedFunctionExpressions: true,
          allowHigherOrderFunctions: true,
          allowDirectConstAssertionInArrowFunctions: true,
          allowIIFEs: true,
        },
      ],
      "@typescript-eslint/no-unused-vars": [
        "error",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
          caughtErrors: "none",
          ignoreRestSiblings: true,
        },
      ],
      "@typescript-eslint/no-non-null-assertion": "error",
      "@typescript-eslint/ban-ts-comment": [
        "error",
        { "ts-expect-error": "allow-with-description" },
      ],
      "@typescript-eslint/no-unnecessary-type-assertion": "error",
      "import/order": [
        "error",
        {
          groups: ["builtin", "external", "internal", ["parent", "sibling", "index"]],
          pathGroups: [{ pattern: "@/**", group: "internal", position: "after" }],
          pathGroupsExcludedImportTypes: ["builtin"],
          "newlines-between": "always",
          alphabetize: { order: "asc", caseInsensitive: true },
        },
      ],
      "import/no-cycle": ["error", { ignoreExternal: true }],
      "import/no-duplicates": ["error", { "prefer-inline": true }],
    },
  },

  /* React, accessibility and the React Compiler rules */
  {
    files: ["src/**/*.tsx", ".storybook/**/*.tsx"],
    rules: {
      ...jsxA11y.flatConfigs.strict.rules,
      "jsx-a11y/label-has-associated-control": [
        "error",
        {
          assert: "either",
          depth: 3,
          controlComponents: ["Checkbox", "Input", "Textarea", "InputGroupInput"],
        },
      ],
      "react/forbid-dom-props": [
        "error",
        {
          forbid: [
            {
              propName: "style",
              message: "Inline styles bypass the design tokens. Use Tailwind classes.",
            },
          ],
        },
      ],
      "react/forbid-component-props": [
        "error",
        {
          forbid: [
            {
              propName: "style",
              message: "Inline styles bypass the design tokens. Use Tailwind classes.",
            },
          ],
        },
      ],
      "react/no-danger": "error",
      "react/jsx-no-leaked-render": ["error", { validStrategies: ["ternary", "coerce"] }],
      "react/jsx-boolean-value": ["error", "never"],
      "react/self-closing-comp": "error",
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "error",
      "react-hooks/static-components": "error",
      "react-hooks/use-memo": "error",
      "react-hooks/preserve-manual-memoization": "error",
      "react-hooks/incompatible-library": "error",
      "react-hooks/immutability": "error",
      "react-hooks/globals": "error",
      "react-hooks/refs": "error",
      "react-hooks/set-state-in-effect": "error",
      "react-hooks/set-state-in-render": "error",
      "react-hooks/purity": "error",
      "react-hooks/error-boundaries": "error",
      "react-hooks/unsupported-syntax": "error",
      "react-hooks/config": "error",
      "react-hooks/gating": "error",
    },
  },

  /* Tailwind: token classes only, no unknown or conflicting classes */
  {
    files: ["src/**/*.{ts,tsx}", ".storybook/**/*.tsx"],
    plugins: { "better-tailwindcss": betterTailwindcss },
    settings: {
      "better-tailwindcss": {
        entryPoint: "src/app/globals.css",
        tsconfig: "tsconfig.json",
        selectors: [
          ...getDefaultSelectors(),
          {
            kind: "variable",
            name: "^\\w*[cC]lasses$",
            match: [{ type: "strings" }, { type: "objectValues" }],
          },
        ],
      },
    },
    rules: {
      "better-tailwindcss/no-unknown-classes": "error",
      "better-tailwindcss/no-conflicting-classes": "error",
      "better-tailwindcss/no-duplicate-classes": "error",
      "better-tailwindcss/no-deprecated-classes": "error",
      "better-tailwindcss/no-unnecessary-whitespace": "error",
      "better-tailwindcss/enforce-shorthand-classes": "error",
      "better-tailwindcss/enforce-canonical-classes": "error",
      "better-tailwindcss/enforce-consistent-variable-syntax": "error",
      "better-tailwindcss/enforce-consistent-important-position": "error",
      "better-tailwindcss/no-restricted-classes": ["error", { restrict: RESTRICTED_CLASSES }],
    },
  },

  /* Source-wide conventions */
  {
    files: SRC_FILES,
    plugins: { local },
    rules: {
      "local/logger-file-matches": "error",
      "no-console": "error",
      "no-restricted-syntax": ["error", FC_SYNTAX, ...FORMAT_SYNTAX, DEFAULT_EXPORT_SYNTAX],
    },
  },
  {
    files: ["src/app/**/*.{ts,tsx}"],
    rules: { "no-restricted-syntax": ["error", FC_SYNTAX, ...FORMAT_SYNTAX] },
  },
  {
    files: ["src/lib/format/**/*.ts"],
    rules: { "no-restricted-syntax": ["error", FC_SYNTAX, DEFAULT_EXPORT_SYNTAX] },
  },
  {
    // Every backend call goes through apiRequest (Data IDs, request IDs, logs, contract checks).
    files: SRC_FILES,
    ignores: ["src/lib/api/**", "src/mocks/**", ...TEST_FILES],
    rules: {
      "no-restricted-globals": [
        "error",
        {
          name: "fetch",
          message: "Call the backend only through apiRequest() in @/lib/api/client.",
        },
      ],
    },
  },
  {
    // queryOptions() factories return inferred TanStack types (with typed query keys);
    // spelling them out by hand loses that typing.
    files: ["src/features/**/api/*.queries.ts"],
    rules: { "@typescript-eslint/explicit-function-return-type": "off" },
  },

  /* Layering */
  boundary(SRC_FILES, [], ""),
  boundary(
    ["src/lib/**/*.{ts,tsx}"],
    ["@/components/**", "@/features/**", "@/app/**", "@/hooks/**", "@/mocks/**"],
    "lib/ is the foundation layer: it must not import components, features, hooks, routes or mocks.",
    { ignores: ["src/lib/utils.ts"] },
  ),
  boundary(
    ["src/lib/utils.ts"],
    ["@/components/**", "@/features/**", "@/app/**", "@/hooks/**", "@/mocks/**"],
    "lib/ is the foundation layer.",
    {
      allow: ["clsx", "tailwind-merge"],
    },
  ),
  boundary(
    ["src/components/ui/**/*.{ts,tsx}"],
    [
      "@/components/patterns/**",
      "@/components/layout/**",
      "@/components/providers/**",
      "@/features/**",
      "@/app/**",
      "@/mocks/**",
    ],
    "ui/ primitives may only use lib/ and hooks/.",
    { ignores: ["src/components/ui/icon.tsx"] },
  ),
  boundary(
    ["src/components/ui/icon.tsx"],
    [
      "@/components/patterns/**",
      "@/components/layout/**",
      "@/components/providers/**",
      "@/features/**",
      "@/app/**",
      "@/mocks/**",
    ],
    "ui/ primitives may only use lib/ and hooks/.",
    { allow: ["@hugeicons/react"] },
  ),
  boundary(
    ["src/components/patterns/**/*.{ts,tsx}"],
    [
      "@/components/layout/**",
      "@/components/providers/**",
      "@/features/**",
      "@/app/**",
      "@/mocks/**",
    ],
    "patterns/ are domain-free: they may use ui/, lib/ and hooks/ only.",
  ),
  boundary(
    ["src/components/layout/**/*.{ts,tsx}"],
    ["@/components/providers/**", "@/app/**", "@/mocks/**"],
    "layout/ may not import providers, routes or mocks.",
  ),
  boundary(
    ["src/components/providers/**/*.{ts,tsx}"],
    ["@/app/**", "@/mocks/**"],
    "providers/ may not import routes or mocks (only mock-gate loads mocks).",
    { ignores: ["src/components/providers/mock-gate.tsx"] },
  ),
  boundary(
    ["src/components/providers/mock-gate.tsx"],
    ["@/app/**"],
    "providers/ may not import routes.",
  ),
  boundary(
    ["src/features/**/*.{ts,tsx}"],
    ["@/app/**", "@/mocks/**", "@/components/layout/**", "@/components/providers/**"],
    "features/ may not import routes, mocks, layout or providers.",
  ),
  boundary(
    ["src/hooks/**/*.{ts,tsx}"],
    ["@/components/**", "@/features/**", "@/app/**", "@/mocks/**"],
    "hooks/ are generic: they may use lib/ only.",
  ),
  boundary(
    ["src/mocks/**/*.{ts,tsx}"],
    ["@/components/**", "@/app/**", "@/hooks/**"],
    "mocks/ may use features' schemas and lib/ only.",
  ),
  boundary(["src/app/**/*.{ts,tsx}"], ["@/mocks/**"], "Routes never import mocks."),

  /* Tests */
  {
    files: TEST_FILES,
    plugins: { vitest, local },
    rules: {
      ...vitest.configs.recommended.rules,
      // Vitest accepts a failure message as the second argument: expect(value, "why").
      "vitest/valid-expect": ["error", { maxArgs: 2 }],
      "vitest/consistent-test-it": ["error", { fn: "it", withinDescribe: "it" }],
      "vitest/no-focused-tests": "error",
      "vitest/no-disabled-tests": "error",
      "vitest/require-top-level-describe": "error",
      "local/test-describe-data-id": "error",
      "local/logger-file-matches": "off",
      "@typescript-eslint/explicit-function-return-type": "off",
      "no-restricted-imports": ["error", { paths: RESTRICTED_PATHS }],
      "no-restricted-syntax": "off",
    },
  },
  {
    files: ["**/*.test.tsx"],
    ...testingLibrary.configs["flat/react"],
  },

  /* Stories */
  {
    files: STORY_FILES,
    rules: {
      "@typescript-eslint/explicit-function-return-type": "off",
      "no-restricted-syntax": ["error", FC_SYNTAX, ...FORMAT_SYNTAX],
    },
  },

  /* Node scripts and config files */
  {
    files: ["scripts/**/*.ts", "**/*.mjs", "*.config.ts", "*.config.mts"],
    languageOptions: { globals: globals.node },
    rules: { "no-console": "off" },
  },

  prettierConfig,
]);

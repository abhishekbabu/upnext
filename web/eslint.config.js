/**
 * Lint rules for the front end.
 *
 * Deliberately short. `tsc` already rejects unused variables, bad imports and
 * wrong types, so this file carries only what it cannot see, and every rule in
 * it is here because something can actually go wrong.
 */
import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

/** Tailwind's own palette, which a theme cannot follow. */
const PALETTE =
  "slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|" +
  "teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose";
const RAW_COLOR = `\\b(text|bg|border|ring|fill|stroke|from|via|to)-(${PALETTE})-[0-9]{2,3}\\b`;
const RAW_COLOR_MESSAGE =
  "Color comes from semantic tokens — bg-card, text-muted-foreground. A raw " +
  "palette utility cannot follow a mode change.";

export default tseslint.config(
  { ignores: ["dist/**", "scripts/**"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: { globals: globals.browser, parserOptions: { ecmaFeatures: { jsx: true } } },
    plugins: { "react-hooks": reactHooks },
    rules: {
      /**
       * `static-components` is the one that bites hardest: a component declared
       * inside another is a new function every render, so React sees a new
       * element type and remounts the subtree — every panel refetching and
       * losing its scroll position, with nothing failing.
       */
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      "react-hooks/static-components": "error",
      "react-hooks/set-state-in-effect": "error",

      "no-restricted-syntax": [
        "error",
        { selector: `Literal[value=/${RAW_COLOR}/]`, message: RAW_COLOR_MESSAGE },
        { selector: `TemplateElement[value.raw=/${RAW_COLOR}/]`, message: RAW_COLOR_MESSAGE },
      ],
    },
  },
);

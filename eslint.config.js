import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";

// Guardrail only: catch identifiers that do not exist. Not a style linter.
export default [
  {
    files: ["drive/src/**/*.{js,jsx}", "e2e/**/*.{js,mjs}", "scripts/**/*.{js,mjs}"],
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: "module",
      globals: { ...globals.browser, ...globals.node },
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    plugins: { "react-hooks": reactHooks },
    rules: {
      "no-undef": "error",
      "no-use-before-define": ["error", { functions: false, classes: false, variables: true }],
    },
  },
];

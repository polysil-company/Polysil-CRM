/** @type {import('lint-staged').Configuration} */
const config = {
  "*.{ts,tsx,mts}": ["eslint --fix --max-warnings=0", "prettier --write --ignore-unknown"],
  "*.{js,mjs,cjs}": ["prettier --write --ignore-unknown"],
  "*.{json,md,mdx,css,yml,yaml}": ["prettier --write --ignore-unknown"],
};

export default config;

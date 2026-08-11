/** lint-staged configuration — staged-file quality checks on pre-commit. */
export default {
  '*.{js,mjs,cjs,ts,mts,cts,jsx,tsx}': ['eslint --fix', 'prettier --write'],
  '*.{json,jsonc,yaml,yml}': ['prettier --write'],
  '*.md': ['prettier --write', 'markdownlint --fix'],
  '*.{css,scss,html,graphql}': ['prettier --write'],
};

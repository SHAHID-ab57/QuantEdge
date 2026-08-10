/** Root shared ESLint flat configuration — framework-agnostic baseline. */
import js from '@eslint/js';

export default [
  {
    ignores: [
      'node_modules/**',
      'dist/**',
      'build/**',
      'out/**',
      'coverage/**',
      '.next/**',
      '.nuxt/**',
      '.venv/**',
      'venv/**',
      '**/__pycache__/**',
      'artifacts/**',
      'datasets/**',
      'models/**',
      'runs/**',
      '*.min.js',
    ],
  },
  js.configs.recommended,
  {
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
    },
    rules: {
      'no-console': 'warn',
      'no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
      eqeqeq: ['error', 'always'],
      curly: ['error', 'all'],
      'no-var': 'error',
      'prefer-const': 'error',
      'prefer-template': 'error',
      'object-shorthand': ['error', 'always'],
      'no-duplicate-imports': 'error',
      'no-else-return': ['error', { allowElseIf: false }],
      'no-nested-ternary': 'error',
      'require-await': 'error',
      'default-case-last': 'error',
      'no-return-await': 'error',
    },
  },
  {
    files: ['**/*.config.{js,mjs,cjs}'],
    languageOptions: {
      sourceType: 'module',
    },
  },
  {
    files: ['**/*.test.{js,mjs,cjs}', '**/__tests__/**', 'tests/**'],
    rules: {
      'no-console': 'off',
    },
  },
];

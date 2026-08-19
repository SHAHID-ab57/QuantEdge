import { FlatCompat } from '@eslint/eslintrc';
import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import prettier from 'eslint-config-prettier';
import rootConfig from '../../eslint.config.mjs';

const baseDirectory = dirname(fileURLToPath(import.meta.url));
const compat = new FlatCompat({ baseDirectory });

export default [
  {
    ignores: ['.next/**', 'next-env.d.ts'],
  },
  ...rootConfig,
  ...compat.extends('next/core-web-vitals', 'next/typescript'),
  prettier,
];

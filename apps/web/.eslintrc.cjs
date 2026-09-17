module.exports = {
  root: true,
  env: { browser: true, es2020: true },
  parser: '@typescript-eslint/parser',
  parserOptions: { ecmaVersion: 'latest', sourceType: 'module' },
  plugins: ['@typescript-eslint', 'react-hooks', 'react-refresh'],
  extends: ['eslint:recommended', 'plugin:@typescript-eslint/recommended', 'plugin:react-hooks/recommended'],
  ignorePatterns: ['dist', 'node_modules'],
  rules: {
    '@typescript-eslint/consistent-type-imports': 'error',
    'react-hooks/exhaustive-deps': 'error',
    'react-refresh/only-export-components': ['error', { allowConstantExport: true }],
    'no-restricted-globals': ['error', { name: 'fetch', message: 'Use a feature API module and the shared HTTP client.' }],
    'no-restricted-imports': ['error', { patterns: ['@/App', '@/app/*'] }],
  },
  overrides: [
    { files: ['src/App.tsx', 'src/app/**'], rules: { 'no-restricted-imports': 'off' } },
    { files: ['src/shared/api/client.ts'], rules: { 'no-restricted-globals': 'off' } },
    {
      files: ['src/shared/**'],
      rules: { 'no-restricted-imports': ['error', { patterns: ['@/App', '@/app/*', '@/features/*', '@/pages/*'] }] },
    },
    {
      files: ['src/**/*.tsx'],
      excludedFiles: ['src/App.tsx', 'src/app/**', 'src/features/auth/AuthProvider.tsx'],
      rules: { 'no-restricted-imports': ['error', { patterns: ['@/App', '@/app/*', '@/shared/api/*'] }] },
    },
  ],
}

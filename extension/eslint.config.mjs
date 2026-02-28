export default [
  {
    ignores: ['dist/**', 'node_modules/**']
  },
  {
    files: ['src/**/*.js'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: {
        chrome: 'readonly',
        window: 'readonly',
        document: 'readonly',
        navigator: 'readonly',
        MutationObserver: 'readonly',
        CustomEvent: 'readonly',
        URL: 'readonly',
        URLSearchParams: 'readonly',
        fetch: 'readonly',
        Blob: 'readonly',
        console: 'readonly',
        self: 'readonly',
        setTimeout: 'readonly',
        clearTimeout: 'readonly',
        alert: 'readonly',
        confirm: 'readonly',
        atob: 'readonly'
      }
    },
    rules: {}
  }
];

module.exports = {
  env: {
    browser: true,
    es2021: true,
    webextensions: true,
    node: true
  },
  
  extends: [
    'eslint:recommended',
    'prettier'
  ],
  
  parserOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module'
  },
  
  plugins: ['prettier'],
  
  rules: {
    // Prettier integration
    'prettier/prettier': ['error', {
      singleQuote: true,
      semi: true,
      trailingComma: 'es5',
      printWidth: 100,
      tabWidth: 2,
      useTabs: false
    }],
    
    // Best practices
    'no-console': ['warn', { allow: ['warn', 'error', 'info', 'debug'] }],
    'no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
    'no-debugger': 'warn',
    'prefer-const': 'error',
    'no-var': 'error',
    'object-shorthand': 'error',
    'prefer-arrow-callback': 'error',
    'prefer-template': 'error',
    
    // Code quality
    'eqeqeq': ['error', 'always'],
    'curly': ['error', 'all'],
    'no-multiple-empty-lines': ['error', { max: 2, maxEOF: 1 }],
    'no-trailing-spaces': 'error',
    'quotes': ['error', 'single', { avoidEscape: true }],
    'semi': ['error', 'always']
  },
  
  globals: {
    chrome: 'readonly',
    browser: 'readonly'
  },
  
  overrides: [
    {
      files: ['webpack.config.js', '.eslintrc.js'],
      env: {
        node: true,
        browser: false
      }
    }
  ]
};
const path = require('path');
const CopyPlugin = require('copy-webpack-plugin');

module.exports = {
  entry: {
    'background/background': './src/background/background.js',
    'content/content': './src/content/content.js',
    'popup/popup': './src/popup/popup.js'
  },
  output: {
    path: path.resolve(__dirname, 'dist'),
    filename: '[name].js',
    clean: true,
    module: true,           // ← Add this
    chunkFormat: 'module'   // ← Add this
  },
  experiments: {
    outputModule: true      // ← Add this
  },
 
  module: {
    rules: [
      {
        test: /\.js$/,
        exclude: /node_modules/,
        use: {
          loader: 'babel-loader',
          options: {
            presets: ['@babel/preset-env']
          }
        }
      }
    ]
  },
  plugins: [
    new CopyPlugin({
      patterns: [
        { from: 'manifest.json', to: 'manifest.json' },
        { from: 'assets', to: 'assets' },
        { from: 'src/content/content.css', to: 'content/content.css' },
        { from: 'src/popup/popup.html', to: 'popup/popup.html' },
        { from: 'src/popup/popup.css', to: 'popup/popup.css' }
      ]
    })
  ],
  optimization: {
    minimize: true
  }
};
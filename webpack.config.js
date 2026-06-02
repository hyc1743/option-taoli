const path = require('path');
const TerserPlugin = require('terser-webpack-plugin');
const WebpackObfuscator = require('webpack-obfuscator');

module.exports = {
  entry: './src/dashboard_client.js',
  output: {
    path: path.resolve(__dirname, 'public'),
    filename: 'dashboard.bundle.js',
  },
  optimization: {
    minimize: true,
    minimizer: [
      new TerserPlugin({
        terserOptions: {
          compress: {
            drop_console: true,
            passes: 2,
          },
          mangle: {
            toplevel: true,
          },
          format: {
            comments: false,
          },
        },
        extractComments: false,
      }),
    ],
  },
  plugins: [
    new WebpackObfuscator({
      compact: true,
      controlFlowFlattening: true,
      deadCodeInjection: true,
      identifierNamesGenerator: 'hexadecimal',
      rotateStringArray: true,
      selfDefending: true,
      splitStrings: true,
      stringArray: true,
      stringArrayEncoding: ['base64'],
      stringArrayThreshold: 0.75,
    }),
  ],
};

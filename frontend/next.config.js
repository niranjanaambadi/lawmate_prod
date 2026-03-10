/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  },
  // 1. Keep this for local/fallback compatibility
  webpack: (config) => {
    config.resolve.fallback = { ...config.resolve.fallback, canvas: false, fs: false, path: false };
    return config;
  },
  // 2. Turbopack resolveAlias — must be module paths, not booleans (webpack syntax)
  // Point node-only modules at a no-op stub so client bundles don't break.
  turbopack: {
    resolveAlias: {
      canvas: { browser: "./src/lib/empty-module.js" },
      fs:     { browser: "./src/lib/empty-module.js" },
    },
  },
};

module.exports = nextConfig;

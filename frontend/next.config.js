/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  },
  // Ensure src/docs/ is included in standalone output file tracing.
  outputFileTracingIncludes: {
    "/dashboard/help-center": ["./src/docs/**"],
  },
  // 1. Stub node-only modules for CLIENT bundles only.
  webpack: (config, { isServer }) => {
    if (!isServer) {
      config.resolve.fallback = { ...config.resolve.fallback, canvas: false, fs: false, path: false };
    }
    return config;
  },
  // 2. Turbopack: only alias canvas on the client; do NOT alias fs — server
  //    components need the real Node fs to read help-center-pages.md.
  turbopack: {
    resolveAlias: {
      canvas: "./src/lib/empty-module.js",
    },
  },
};

module.exports = nextConfig;

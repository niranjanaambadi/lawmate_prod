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
  // 2. Turbopack: alias node-only modules for client bundles (e.g. html-to-docx uses fs).
  //    resolveAlias only affects client bundles in Next.js — server components
  //    still get the real Node fs, so help-center-pages.md can be read normally.
  turbopack: {
    resolveAlias: {
      canvas: "./src/lib/empty-module.js",
      fs:     "./src/lib/empty-module.js",
    },
  },
};

module.exports = nextConfig;

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
  // 2. Add this for Vercel's default Turbopack build
  turbopack: {
    resolveAlias: {
      canvas: false,
      fs: false,
      path: false,
    },
  },
};

module.exports = nextConfig;

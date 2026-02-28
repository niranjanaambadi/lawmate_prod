/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  },
  // Keep webpack for backward compatibility if you toggle flags
  webpack: (config) => {
    config.resolve.fallback = {
      ...config.resolve.fallback,
      canvas: false,
      fs: false,
      path: false,
    };
    return config;
  },
  // Add this for Next.js 16+ Turbopack support
  experimental: {
    turbopack: {
      resolveAlias: {
        canvas: false,
      },
    },
  },
};

module.exports = nextConfig;

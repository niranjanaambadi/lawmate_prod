/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  },
  webpack: (config) => {
    config.resolve = config.resolve || {};
    config.resolve.alias = {
      ...(config.resolve.alias || {}),
      canvas: false,
    };
    config.resolve.fallback = {
      ...(config.resolve.fallback || {}),
      canvas: false,
      fs: false,
      path: false,
    };
    return config;
  },
};

module.exports = nextConfig;

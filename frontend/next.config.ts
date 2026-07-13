/** @type {import('next').NextConfig} */
const nextConfig = {
  env: {
    FASTAPI_URL: process.env.FASTAPI_URL || "http://127.0.0.1:8000",
  },
};

export default nextConfig;

/** @type {import('next').NextConfig} */
const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND_URL}/api/:path*`,
      },
    ];
  },
  // The app only uses plain <img>, so the image optimizer is switched off:
  // /_next/image answers 404 and the server never fetches a remote URL.
  // Do not add remotePatterns here without a strict host allowlist.
  images: {
    unoptimized: true,
  },
};

export default nextConfig;

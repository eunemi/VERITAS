import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Give a parallel preview its own generated output; never share runtime chunks
  // between the host dev server and a sandbox or a different bundler.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  allowedDevOrigins: [
    "*.ngrok-free.app",
    "*.ngrok-free.dev",
    "*.ngrok.app",
    "*.ngrok.io",
    "*.trycloudflare.com",
  ],
  experimental: {
    serverActions: {
      allowedOrigins: [
        "*.ngrok-free.app",
        "*.ngrok-free.dev",
        "*.ngrok.app",
        "*.ngrok.io",
        "*.trycloudflare.com",
      ],
    },
  },
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: "http://127.0.0.1:8000/api/v1/:path*",
      },
      {
        source: "/api/health",
        destination: "http://127.0.0.1:8000/api/health",
      },
      {
        source: "/health",
        destination: "http://127.0.0.1:8000/health",
      },
    ];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
};

export default nextConfig;

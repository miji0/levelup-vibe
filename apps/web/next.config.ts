import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  distDir: process.env.E2E_DIST_DIR || ".next",
  // Vercel Services owns production routing; this fixed loopback rewrite is local-only.
  async rewrites() {
    return process.env.NODE_ENV === "development"
      ? [
          {
            source: "/api/:path*",
            destination: `http://127.0.0.1:${process.env.E2E_API_PORT || "8000"}/api/:path*`,
          },
        ]
      : [];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "X-Frame-Options", value: "DENY" },
        ],
      },
    ];
  },
};
export default nextConfig;

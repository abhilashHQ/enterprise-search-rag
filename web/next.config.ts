import type { NextConfig } from "next"

const ORGBRAIN_API_URL = process.env.ORGBRAIN_API_URL ?? "http://127.0.0.1:8000"

const nextConfig: NextConfig = {
  devIndicators: { position: "bottom-right" },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${ORGBRAIN_API_URL}/api/:path*` }]
  },
}

export default nextConfig

import type { NextConfig } from "next";

// Server-side proxy target for /api/* (see rewrites below).
const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  trailingSlash: true,
  images: { unoptimized: true },
  // Proxy browser API calls through this app's own origin so Django's
  // httpOnly auth cookies are first-party. Cross-site they'd be dropped:
  // SameSite=Lax cookies never ride on vercel.app → onrender.com fetches.
  async rewrites() {
    return [
      { source: "/api/:path*/", destination: `${API_URL}/api/:path*/` },
      { source: "/api/:path*", destination: `${API_URL}/api/:path*` },
      // Django admin on the site's own domain. /static/ is Django's
      // STATIC_URL (whitenoise) — admin CSS/JS live there. The bare
      // /admin/ rule must come first: :path*/ matches it with an empty
      // path, and the resulting /admin// 404s for authenticated users.
      { source: "/admin/", destination: `${API_URL}/admin/` },
      { source: "/admin/:path*/", destination: `${API_URL}/admin/:path*/` },
      { source: "/admin/:path*", destination: `${API_URL}/admin/:path*` },
      { source: "/static/:path*", destination: `${API_URL}/static/:path*` },
    ];
  },
};

export default nextConfig;

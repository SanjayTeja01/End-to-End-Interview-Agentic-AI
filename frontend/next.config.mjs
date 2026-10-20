/** @type {import('next').NextConfig} */
// The browser talks to the backend through this same-origin proxy (/api/*), so the httpOnly refresh
// cookie is first-party. Only NEXT_PUBLIC_* values ever reach the browser; no backend secret is read here.
const backend = process.env.BACKEND_INTERNAL_URL || "http://localhost:8000";

const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/:path*` }];
  },
  async headers() {
    return [{
      source: "/:path*",
      headers: [
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "Referrer-Policy", value: "same-origin" },
        { key: "Permissions-Policy", value: "camera=(self), microphone=(self), geolocation=()" },
      ],
    }];
  },
};

export default nextConfig;

import type { NextConfig } from 'next';

// Server-side routing configuration. Never use NEXT_PUBLIC_ for the API key.
const backend = process.env.BACKEND_URL?.replace(/\/+$/, '') || 'http://127.0.0.1:8000';
const parsed = new URL(backend);
if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password || parsed.search || parsed.hash || parsed.pathname !== '/') {
  throw new Error('BACKEND_URL must be an HTTP(S) origin, for example https://api.example.com, without credentials or a path.');
}
if (process.env.VERCEL && (!process.env.BACKEND_URL || parsed.protocol !== 'https:' || ['localhost', '127.0.0.1', '::1'].includes(parsed.hostname))) {
  throw new Error('Set BACKEND_URL to your publicly hosted HTTPS FastAPI origin in Vercel project settings. The local Python server is not deployed with the frontend.');
}
const config: NextConfig = {
  devIndicators: false,
  async rewrites() {
    return [{ source: '/api/:path*', destination: `${backend}/api/:path*` }];
  },
};
export default config;

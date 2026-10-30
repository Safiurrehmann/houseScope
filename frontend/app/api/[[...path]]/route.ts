import type { NextRequest } from 'next/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const hopByHop = [
  'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
  'te', 'trailer', 'transfer-encoding', 'upgrade',
];

function forwardedHeaders(original: Headers): Headers {
  const headers = new Headers(original);
  // Connection can name additional connection-specific headers.
  for (const name of (headers.get('connection') || '').split(',')) {
    if (name.trim()) headers.delete(name.trim());
  }
  for (const name of hopByHop) headers.delete(name);
  headers.delete('host');
  return headers;
}

type Context = { params: Promise<{ path?: string[] }> };

async function proxy(request: NextRequest, context: Context): Promise<Response> {
  // Read the binding here, never at module evaluation or during next build.
  const binding = process.env.BACKEND_URL;
  if (!binding && process.env.VERCEL) {
    return Response.json({ detail: 'Backend service binding is unavailable. Configure frontend → backend as BACKEND_URL.' }, { status: 503 });
  }
  const base = binding || 'http://127.0.0.1:8000/'; // Standalone local start.sh only.
  let target: URL;
  try {
    const parsed = new URL(base);
    if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password || parsed.search || parsed.hash) {
      throw new Error('Invalid service URL');
    }
    const { path = [] } = await context.params;
    if (path.some(segment => segment === '.' || segment === '..')) {
      return Response.json({ detail: 'Invalid API path' }, { status: 400 });
    }
    // Backend owns /api/*. The binding targets the service base, not a public
    // mount. Preserve any internal base path and append exactly one API path.
    target = new URL(`api${path.length ? '/' + path.map(encodeURIComponent).join('/') : ''}`, base.replace(/\/?$/, '/'));
    target.search = new URL(request.url).search;
  } catch {
    return Response.json({ detail: 'Backend service URL is invalid.' }, { status: 503 });
  }
  try {
    const options: RequestInit & { duplex?: 'half' } = {
      method: request.method,
      headers: forwardedHeaders(request.headers),
      redirect: 'manual',
      cache: 'no-store',
      signal: request.signal,
    };
    if (request.method !== 'GET' && request.method !== 'HEAD' && request.body) {
      options.body = request.body;
      options.duplex = 'half';
    }
    const upstream = await fetch(target, options);
    const headers = forwardedHeaders(upstream.headers);
    // fetch may decompress upstream responses. Do not forward stale wire sizes.
    headers.delete('content-encoding');
    headers.delete('content-length');
    headers.set('cache-control', 'private, no-store');
    const location = headers.get('location');
    if (location) {
      const redirect = new URL(location, target);
      const internalPrefix = new URL(base).pathname.replace(/\/$/, '');
      if (redirect.origin === target.origin && redirect.pathname.startsWith(internalPrefix + '/api')) {
        // Keep FastAPI's slash redirects on the public origin, not its private URL.
        headers.set('location', redirect.pathname.slice(internalPrefix.length) + redirect.search + redirect.hash);
      }
    }
    return new Response(request.method === 'HEAD' || [204, 205, 304].includes(upstream.status) ? null : upstream.body, {
      status: upstream.status,
      headers,
    });
  } catch {
    // Do not expose the internal binding URL or upstream credential details.
    return Response.json({ detail: 'Backend service is unavailable.' }, { status: 502 });
  }
}

export { proxy as GET, proxy as HEAD, proxy as POST, proxy as PUT, proxy as PATCH, proxy as DELETE, proxy as OPTIONS };

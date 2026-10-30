import type { NextConfig } from 'next';

// Service bindings exist only inside runtime functions. The API route handler
// resolves BACKEND_URL per request; neither builds nor middleware read it.
const config: NextConfig = { devIndicators: false };
export default config;

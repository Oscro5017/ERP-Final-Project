import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const apiTarget = process.env.ERP_API_PROXY_TARGET || 'http://127.0.0.1:8000';
// First path segment of every backend endpoint. backend/tests/test_web_dev_proxy.py fails when one is missing.
const apiPrefixes = [
  '/auth',
  '/crop-cycles',
  '/customers',
  '/tables',
  '/batches',
  '/crop-types',
  '/activities',
  '/input-catalog',
  '/tasks',
  '/weather',
  '/sensors',
  '/products',
  '/suppliers',
  '/trade',
  '/sales-orders',
  '/freshness',
  '/preferences',
  '/stock',
  '/finance',
  '/dashboard',
  '/insights',
  '/notifications',
  '/push-devices',
];

// Opening or refreshing a page in the browser asks for HTML, so pages such as /insights or /finance
// load the app even though API paths start the same way. API calls ask for JSON and are proxied.
const servePage = (request) => (request.headers.accept?.includes('text/html') ? '/index.html' : undefined);

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.js',
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    proxy: Object.fromEntries(apiPrefixes.map((path) => [path, { target: apiTarget, changeOrigin: true, bypass: servePage }])),
  },
});

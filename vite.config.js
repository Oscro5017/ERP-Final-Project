import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const apiTarget = process.env.ERP_API_PROXY_TARGET || 'http://127.0.0.1:8000';
const apiPrefixes = [
  '/auth',
  '/crop-cycles',
  '/customers',
  '/tables',
  '/batches',
  '/crop-types',
  '/input-applications',
  '/input-catalog',
  '/tasks',
  '/weather/',
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
];

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'frontend',
    emptyOutDir: true,
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    proxy: Object.fromEntries(apiPrefixes.map((path) => [path, { target: apiTarget, changeOrigin: true }])),
  },
});

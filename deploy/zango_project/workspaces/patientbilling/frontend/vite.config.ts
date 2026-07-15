import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import tailwindcss from '@tailwindcss/vite'


export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  
  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    esbuild: {
      loader: 'tsx',
      include: /src\/.*\.[jt]sx?$/,
      exclude: [],
    },
    optimizeDeps: {
      include: ['@zango-core/crm-framework'],
      esbuildOptions: {
        loader: {
          '.js': 'jsx',
          '.ts': 'tsx',
          '.tsx': 'tsx',
        },
      },
    },
    server: {
      port: 3000,
      proxy: (() => {
        const target = env.VITE_API_BASE_URL || 'http://localhost:8000';
        const proxyConfig = {
          target,
          changeOrigin: true,
          secure: false,
        };
        
        // Get API routes from environment variable or use defaults
        const proxyRoutes = env.VITE_PROXY_ROUTES || '/api,/zango,/frame';
        const apiRoutes = proxyRoutes.split(',').map(route => route.trim());
        
        // Create a proxy configuration for each API route
        const config: Record<string, typeof proxyConfig> = {};
        apiRoutes.forEach(route => {
          config[route] = proxyConfig;
        });
        
        return config;
      })(),
    },
    build: {
      outDir: 'dist',
      sourcemap: true,
    },
  };
});
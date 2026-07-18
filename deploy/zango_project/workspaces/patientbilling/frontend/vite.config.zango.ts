import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { viteSingleFile } from 'vite-plugin-singlefile';
import cssInjectedByJsPlugin from 'vite-plugin-css-injected-by-js';
import path from 'path';

// Configuration for building as a single file for Zango platform
export default defineConfig({
  plugins: [
    react(),
    cssInjectedByJsPlugin(),
    viteSingleFile({
      removeViteModuleLoader: true,
      useRecommendedBuildConfig: false, // Don't use recommended config to avoid HTML inlining
    })
  ],
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
  build: {
    outDir: 'zango-build',
    rollupOptions: {
      input: path.resolve(__dirname, 'src/index.zango.tsx'),
      output: {
        manualChunks: undefined,
        inlineDynamicImports: true,
        entryFileNames: 'zango-app.min.js',
        assetFileNames: '[name][extname]',
        format: 'iife',
      },
    },
    target: 'es2015',
    minify: 'terser',
    cssCodeSplit: false,
    assetsInlineLimit: 100000000,
    chunkSizeWarningLimit: 100000000,
    reportCompressedSize: false,
    modulePreload: false,
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  define: {
    global: 'globalThis',
  },
});

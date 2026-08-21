/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  optimizeDeps: {
    exclude: ["lucide-react", "@countrystatecity/countries"],
  },
  build: {
    outDir: "dist",
    assetsDir: "assets",
    sourcemap: false,
    chunkSizeWarningLimit: 500, // Lower limit to 500KB to catch large chunks
    rollupOptions: {
      output: {
        manualChunks: {
          // ==========================================
          // CORE FRAMEWORK - Load first, cached aggressively
          // ==========================================
          'react-core': ['react', 'react-dom'],
          'react-router': ['react-router-dom'],

          // ==========================================
          // DATA LAYER - Separate for better caching
          // ==========================================
          'data-query': ['@tanstack/react-query'],
          'data-api': ['axios', '@supabase/supabase-js'],

          // ==========================================
          // UI COMPONENTS - Split by weight
          // ==========================================
          'ui-icons': ['lucide-react'], // Icons are large, separate them
          'ui-utils': ['react-hot-toast', 'date-fns', 'react-datepicker'],

          // ==========================================
          // RICH TEXT EDITOR - Keep together to avoid undefined dependencies
          // ==========================================
          'editor-complete': [
            '@tiptap/react',
            '@tiptap/starter-kit',
            '@tiptap/extension-color',
            '@tiptap/extension-highlight',
            '@tiptap/extension-image',
            '@tiptap/extension-link',
            '@tiptap/extension-table',
            '@tiptap/extension-table-row',
            '@tiptap/extension-table-header',
            '@tiptap/extension-table-cell'
          ],

          // ==========================================
          // CHARTS & VISUALIZATION
          // ==========================================
          'charts': ['chart.js', 'react-chartjs-2']
        },
      },
    },

    // ==========================================
    // MINIFICATION & OPTIMIZATION
    // ==========================================
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: false,     // KEEP console.log in production for debugging
        drop_debugger: true,     // Remove debugger statements  
        passes: 2                // Run compression twice for better results
      },
      mangle: {
        safari10: true           // Safari 10 compatibility
      },
      format: {
        comments: false          // Remove all comments
      }
    },

    // ==========================================
    // TARGET MODERN BROWSERS FOR SMALLER BUNDLE
    // ==========================================
    target: 'es2015',
    cssCodeSplit: true,          // Split CSS for better caching
  },
  server: {
    historyApiFallback: true,
    proxy: {
      "/auth": {
        target: "http://localhost:3000",
        changeOrigin: true,
      },
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    pool: "threads",
    include: ["tests/**/*.spec.ts", "tests/**/*.spec.tsx"],
    setupFiles: ["tests/setup.ts"],
  },
  // Define global variables to avoid undefined errors
  define: {
    global: "globalThis",
    'process.env': {
      NODE_ENV: JSON.stringify(process.env.NODE_ENV || 'development'),
      REACT_APP_VERSION: JSON.stringify(process.env.REACT_APP_VERSION || '1.0.0'),
      VITE_APP_VERSION: JSON.stringify(process.env.VITE_APP_VERSION || '1.0.0'),
    },
  },
});

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

export default defineConfig({
  plugins: [
    vue(),
    AutoImport({ resolvers: [ElementPlusResolver()] }),
    Components({ resolvers: [ElementPlusResolver()] })
  ],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  server: {
    port: 5173,
    strictPort: true,
    host: '127.0.0.1',
    proxy: {
      '/tutor-api': {
        target: 'http://127.0.0.1:8600',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/tutor-api/, '/api')
      },
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path
      }
    }
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          katex: ['katex', 'marked-katex-extension'],
          highlight: ['highlight.js', 'marked-highlight']
        }
      }
    }
  },
  test: {
    environment: 'jsdom',
    clearMocks: true,
    include: ['src/**/*.test.js']
  }
})

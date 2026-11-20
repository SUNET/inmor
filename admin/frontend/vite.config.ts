import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  return {
    plugins: [vue()],
    server: {
      port: 5173,
      host: true,
      proxy: {
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true,
        },
      },
    },
    build: {
      sourcemap: false,
      rolldownOptions: {
        output: {
          codeSplitting: {
            groups: [{
              name: 'vendor',
              test: /node_modules\/(vue|vue-router)\//,
              includeDependenciesRecursively: true,
            }],
          },
        },
      },
    },
    define: {
      // Make the API URL available at runtime
      // Use same origin for dev (proxy configured above), or explicit URL for production
      __API_URL__: JSON.stringify(env.VITE_API_URL || ''),
    },
  }
})

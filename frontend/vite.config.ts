import { defineConfig, loadEnv } from "vite"
import react from "@vitejs/plugin-react"
import path from "path"

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "")
  const apiTarget = env.VITE_API_BASE_URL || "http://localhost:8000"

  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    server: {
      port: 3100,
      strictPort: true,
      host: "127.0.0.1",
      proxy: {
        "/api-proxy": {
          target: apiTarget,
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/api-proxy/, ""),
        },
      },
    },
  }
})

import React from "react"
import ReactDOM from "react-dom/client"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { AuthProvider } from "./providers/AuthProvider"
import { TenantProvider } from "./providers/TenantProvider"
import { ThemeProvider } from "./providers/ThemeProvider"
import App from "./App.tsx"
import "./index.css"

// Debug logging
console.log("🚀 React app starting...")
console.log("API URL:", import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL || "http://localhost:8000")
console.log("Root element:", document.getElementById("root"))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 5 * 60 * 1000, // 5 minutes
      // No timeout - wait indefinitely for queries
      networkMode: 'online',
    },
  },
})

const rootElement = document.getElementById("root")
if (!rootElement) {
  throw new Error("Root element not found!")
}

try {
  ReactDOM.createRoot(rootElement).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <TenantProvider>
            <ThemeProvider>
              <App />
            </ThemeProvider>
          </TenantProvider>
        </AuthProvider>
      </QueryClientProvider>
    </React.StrictMode>,
  )
  console.log("✅ React app rendered successfully")
} catch (error) {
  console.error("❌ Failed to render React app:", error)
  rootElement.innerHTML = `
    <div style="padding: 20px; font-family: monospace;">
      <h1>Error Loading App</h1>
      <pre>${error instanceof Error ? error.message : String(error)}</pre>
      <pre>${error instanceof Error ? error.stack : ''}</pre>
    </div>
  `
}


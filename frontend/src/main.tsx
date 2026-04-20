import React from "react"
import ReactDOM from "react-dom/client"
import { QueryClientProvider } from "@tanstack/react-query"
import { Toaster } from "sonner"
import "@/lib/i18n"
import { queryClient } from "@/lib/query-client"
import { AuthProvider } from "@/providers/AuthProvider"
import { TenantProvider } from "@/providers/TenantProvider"
import { ThemeProvider } from "@/providers/ThemeProvider"
import App from "./App"
import "./index.css"
import "./styles/themes.css"

const el = document.getElementById("root")
if (!el) throw new Error("Root element not found")

ReactDOM.createRoot(el).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AuthProvider>
          <TenantProvider>
            <App />
            <Toaster
              theme="dark"
              position="bottom-right"
              richColors
              toastOptions={{
                style: {
                  background: "hsl(var(--surface-3))",
                  border: "1px solid hsl(var(--border))",
                  color: "hsl(var(--foreground))",
                  fontSize: "12px",
                },
              }}
            />
          </TenantProvider>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  </React.StrictMode>,
)

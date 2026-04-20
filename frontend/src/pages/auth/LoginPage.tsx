import { FormEvent, useState } from "react"
import { Navigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { KeyRound, LogIn, Sparkles } from "lucide-react"
import { useAuth } from "@/providers/AuthProvider"
import { cn } from "@/lib/utils"
import nordVerde from "@/assets/nord-verde.png"

export function LoginPage() {
  const { t } = useTranslation()
  const { isAuthenticated, loginWithToken, loginWithCredentials } = useAuth()
  const [mode, setMode] = useState<"password" | "token">("password")
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [token, setToken] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const devToken = import.meta.env.VITE_DEV_TOKEN as string | undefined

  if (isAuthenticated) return <Navigate to="/" replace />

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      if (mode === "password") await loginWithCredentials(username, password)
      else await loginWithToken(token)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : t("errors.generic")
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="grid min-h-screen grid-cols-1 bg-white lg:grid-cols-2">
      {/* Left — brand pane (Nord green + white logo, no body copy) */}
      <div
        className="relative hidden overflow-hidden lg:block"
        style={{
          backgroundColor: "#015736",
          backgroundImage: `url(${nordVerde})`,
          backgroundSize: "cover",
          backgroundPosition: "center",
          backgroundRepeat: "no-repeat",
        }}
      >
        <span className="sr-only">Nord Ventures</span>
      </div>

      {/* Right — form on white */}
      <div className="flex items-center justify-center bg-white p-6">
        <div className="w-full max-w-sm">
          <div className="mb-8">
            <h1 className="text-xl font-semibold">{t("auth.signin_title")}</h1>
            <p className="mt-1 text-sm text-muted-foreground">{t("auth.signin_subtitle")}</p>
          </div>

          <div className="mb-4 flex items-center gap-1 rounded-md border border-border bg-surface-2 p-1 text-[12px]">
            <button
              className={cn(
                "flex-1 rounded-sm px-2 py-1.5 font-medium transition-colors",
                mode === "password" ? "bg-background text-foreground shadow-soft" : "text-muted-foreground",
              )}
              onClick={() => setMode("password")}
            >Usuário / Senha</button>
            <button
              className={cn(
                "flex-1 rounded-sm px-2 py-1.5 font-medium transition-colors",
                mode === "token" ? "bg-background text-foreground shadow-soft" : "text-muted-foreground",
              )}
              onClick={() => setMode("token")}
            >API Token</button>
          </div>

          <form onSubmit={onSubmit} className="space-y-3">
            {mode === "password" ? (
              <>
                <label className="block">
                  <span className="mb-1 block text-[12px] font-medium text-muted-foreground">{t("auth.username")}</span>
                  <input
                    autoFocus
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    className="h-9 w-full rounded-md border border-border bg-background px-2.5 text-[13px] outline-none focus:border-ring"
                  />
                </label>
                <label className="block">
                  <span className="mb-1 block text-[12px] font-medium text-muted-foreground">{t("auth.password")}</span>
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="h-9 w-full rounded-md border border-border bg-background px-2.5 text-[13px] outline-none focus:border-ring"
                  />
                </label>
              </>
            ) : (
              <label className="block">
                <span className="mb-1 block text-[12px] font-medium text-muted-foreground">Token</span>
                <div className="relative">
                  <KeyRound className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                  <input
                    autoFocus
                    value={token}
                    onChange={(e) => setToken(e.target.value)}
                    placeholder="d7a14959..."
                    className="h-9 w-full rounded-md border border-border bg-background pl-8 pr-2.5 text-[13px] font-mono outline-none focus:border-ring"
                  />
                </div>
              </label>
            )}

            {error && (
              <div className="rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-[12px] text-danger">{error}</div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="inline-flex h-9 w-full items-center justify-center gap-2 rounded-md bg-primary text-[13px] font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
            >
              <LogIn className="h-3.5 w-3.5" />
              {t("auth.login")}
            </button>

            {devToken && (
              <button
                type="button"
                onClick={() => { setLoading(true); loginWithToken(devToken).finally(() => setLoading(false)) }}
                className="inline-flex h-9 w-full items-center justify-center gap-2 rounded-md border border-primary/30 bg-primary/10 text-[12px] font-medium text-primary hover:bg-primary/15"
              >
                <Sparkles className="h-3.5 w-3.5" />
                {t("auth.dev_mode_active")}
              </button>
            )}
          </form>
        </div>
      </div>
    </div>
  )
}

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react"
import { api, getStoredToken, setStoredToken } from "@/lib/api-client"

export interface User {
  id: number
  username: string
  email?: string
  is_superuser?: boolean
  is_staff?: boolean
}

interface AuthContextType {
  user: User | null
  token: string | null
  isAuthenticated: boolean
  loginWithToken: (token: string) => Promise<void>
  loginWithCredentials: (username: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)
const USER_KEY = "nord.auth.user"

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => getStoredToken())
  const [user, setUser] = useState<User | null>(() => {
    const raw = localStorage.getItem(USER_KEY)
    if (!raw) return null
    try { return JSON.parse(raw) as User } catch { return null }
  })

  const fetchProfile = useCallback(async () => {
    try {
      // Preferred: DRF auth/me endpoint is common; fall back to inspecting token.
      const me = await api.get<User>("/api/auth/me/").catch(() => null)
      if (me) {
        setUser(me)
        localStorage.setItem(USER_KEY, JSON.stringify(me))
        return
      }
      // If /api/auth/me/ not available, stash a placeholder so the UI can render.
      const placeholder: User = { id: 0, username: "dev" }
      setUser(placeholder)
      localStorage.setItem(USER_KEY, JSON.stringify(placeholder))
    } catch {
      // Silent — UI handles unauthenticated state via token presence.
    }
  }, [])

  useEffect(() => {
    if (token && !user) void fetchProfile()
  }, [token, user, fetchProfile])

  const loginWithToken = useCallback(async (t: string) => {
    setStoredToken(t)
    setToken(t)
    await fetchProfile()
  }, [fetchProfile])

  const loginWithCredentials = useCallback(async (username: string, password: string) => {
    // DRF obtain_auth_token returns {token}; we send it back as Authorization: Token <key>.
    const res = await api.post<{ token: string }>("/api/token/", { username, password })
    setStoredToken(res.token)
    setToken(res.token)
    await fetchProfile()
  }, [fetchProfile])

  const logout = useCallback(() => {
    setStoredToken(null)
    setToken(null)
    setUser(null)
    localStorage.removeItem(USER_KEY)
  }, [])

  const value = useMemo<AuthContextType>(() => ({
    user,
    token,
    isAuthenticated: !!token,
    loginWithToken,
    loginWithCredentials,
    logout,
  }), [user, token, loginWithToken, loginWithCredentials, logout])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within AuthProvider")
  return ctx
}

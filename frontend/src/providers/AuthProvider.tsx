import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react"
import { api, getStoredToken, setStoredToken } from "@/lib/api-client"

export interface User {
  id: number
  username: string
  email?: string | null
  first_name?: string
  last_name?: string
  /** Server-provided "display name" — full name if set, else username.
   *  Falls back to ``username`` when the backend is older and doesn't
   *  return it. */
  display_name?: string
  is_superuser?: boolean
  is_staff?: boolean
}

interface AuthContextType {
  user: User | null
  token: string | null
  isAuthenticated: boolean
  /** Platform-admin gate. Mirrors the backend decision: superuser is the
   *  single source of truth for "can see /admin/*". Derived from
   *  ``user.is_superuser`` (undefined before the profile lands). */
  isSuperuser: boolean
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
      // /api/auth/me/ is the canonical profile source (backend
      // CurrentUserView). A null result here means the token is
      // invalid, the endpoint is down, or the network failed —
      // either way we CANNOT grant a synthetic identity because
      // that broke ``SuperuserGuard`` (the old ``{username: "dev"}``
      // placeholder had no ``is_superuser`` field, so real admins
      // hit "Área restrita" while unauth'd users saw "dev" in the
      // header). If we can't confirm who we are, log the user out
      // so the login screen handles re-auth deterministically.
      const me = await api.get<User>("/api/auth/me/").catch(() => null)
      if (me && me.id) {
        setUser(me)
        localStorage.setItem(USER_KEY, JSON.stringify(me))
        return
      }
      // Couldn't confirm identity → clear token so the UI routes
      // to /login. Prevents a ghost session with no real user.
      setStoredToken(null)
      setToken(null)
      setUser(null)
      localStorage.removeItem(USER_KEY)
    } catch {
      setStoredToken(null)
      setToken(null)
      setUser(null)
      localStorage.removeItem(USER_KEY)
    }
  }, [])

  useEffect(() => {
    // Always re-verify against ``/api/auth/me/`` on mount when a
    // token is present, even if we have a cached ``user``. Rationale:
    //   1. The cached payload may be stale if the backend's User
    //      model gained new fields (e.g. ``is_superuser`` landing on
    //      an already-logged-in session).
    //   2. An earlier build shipped a bogus ``{username: "dev"}``
    //      placeholder when /api/auth/me/ 404s; those stale blobs
    //      are still in user localStorage. Re-verifying on every
    //      mount pulls the real user + self-heals the cache.
    //   3. If the token was revoked server-side, the refetch 401s
    //      and ``fetchProfile`` logs us out — deterministic.
    if (token) void fetchProfile()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

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
    isSuperuser: !!user?.is_superuser,
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

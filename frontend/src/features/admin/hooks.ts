import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { adminApi, type AdminUser, type AdminUserWritable } from "./api"

const KEY_USERS = ["admin", "users"] as const
const KEY_COMPANIES = ["admin", "companies"] as const

/** Search is debounced upstream; this hook just reacts to a stable ``q``. */
export function useAdminUsers(q: string = "") {
  return useQuery({
    queryKey: [...KEY_USERS, q],
    queryFn: () => adminApi.listUsers(q || undefined),
    staleTime: 30_000,
  })
}

export function useAdminCompanies() {
  return useQuery({
    queryKey: KEY_COMPANIES,
    queryFn: () => adminApi.listCompanies(),
    staleTime: 5 * 60_000,
  })
}

export function useSaveAdminUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (input: { id?: number; body: AdminUserWritable }) => {
      if (input.id) return adminApi.updateUser(input.id, input.body)
      return adminApi.createUser(input.body)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY_USERS }),
  })
}

export function useDeactivateAdminUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => adminApi.deactivateUser(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY_USERS }),
  })
}

export function useSetAdminUserActive() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (args: { id: number; isActive: boolean }) =>
      adminApi.setActive(args.id, args.isActive),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY_USERS }),
  })
}

export function useResetAdminUserPassword() {
  return useMutation({
    mutationFn: (id: number) => adminApi.resetPassword(id),
    // No cache invalidation: the password itself is only in the response body.
  })
}

export type { AdminUser }

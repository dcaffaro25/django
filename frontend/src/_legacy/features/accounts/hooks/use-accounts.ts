import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useTenant } from "@/providers/TenantProvider"
import type { Account, PaginatedResponse } from "@/types"
import { useToast } from "@/components/ui/use-toast"
import * as accountApi from "../api"

export function useAccounts(params?: Record<string, unknown>) {
  const { tenant } = useTenant()
  
  return useQuery({
    queryKey: ["accounts", tenant?.subdomain, params],
    queryFn: () => accountApi.getAccounts(tenant!.subdomain, params),
    enabled: !!tenant,
  })
}

export function useAccount(id: number) {
  const { tenant } = useTenant()
  
  return useQuery({
    queryKey: ["account", tenant?.subdomain, id],
    queryFn: () => accountApi.getAccount(tenant!.subdomain, id),
    enabled: !!tenant && !!id,
  })
}

export function useCreateAccount() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: (data: Partial<Account>) =>
      accountApi.createAccount(tenant!.subdomain, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["accounts", tenant?.subdomain] })
      toast({
        title: "Success",
        description: "Account created successfully",
      })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to create account",
        variant: "destructive",
      })
    },
  })
}

export function useUpdateAccount() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<Account> }) =>
      accountApi.updateAccount(tenant!.subdomain, id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["accounts", tenant?.subdomain] })
      toast({
        title: "Success",
        description: "Account updated successfully",
      })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to update account",
        variant: "destructive",
      })
    },
  })
}

export function useDeleteAccount() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: (id: number) => accountApi.deleteAccount(tenant!.subdomain, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["accounts", tenant?.subdomain] })
      toast({
        title: "Success",
        description: "Account deleted successfully",
      })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to delete account",
        variant: "destructive",
      })
    },
  })
}


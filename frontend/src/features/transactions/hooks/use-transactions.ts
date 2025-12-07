import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useTenant } from "@/providers/TenantProvider"
import type { Transaction, PaginatedResponse } from "@/types"
import { useToast } from "@/components/ui/use-toast"
import * as transactionApi from "../api"

// Transactions feature hooks

export function useTransactions(params?: Record<string, unknown>) {
  const { tenant } = useTenant()
  
  return useQuery({
    queryKey: ["transactions", tenant?.subdomain, params],
    queryFn: () => {
      console.log("useTransactions - Fetching transactions for tenant:", tenant!.subdomain, "with params:", params)
      return transactionApi.getTransactions(tenant!.subdomain, params)
    },
    enabled: !!tenant,
    retry: 1,
    retryDelay: 1000,
  })
}

export function useTransaction(id: number) {
  const { tenant } = useTenant()
  
  return useQuery({
    queryKey: ["transaction", tenant?.subdomain, id],
    queryFn: () => transactionApi.getTransaction(tenant!.subdomain, id),
    enabled: !!tenant && !!id,
  })
}

export function useCreateTransaction() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: (data: Partial<Transaction>) =>
      transactionApi.createTransaction(tenant!.subdomain, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["transactions", tenant?.subdomain] })
      toast({
        title: "Success",
        description: "Transaction created successfully",
      })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to create transaction",
        variant: "destructive",
      })
    },
  })
}

export function useUpdateTransaction() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<Transaction> }) =>
      transactionApi.updateTransaction(tenant!.subdomain, id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["transactions", tenant?.subdomain] })
      toast({
        title: "Success",
        description: "Transaction updated successfully",
      })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to update transaction",
        variant: "destructive",
      })
    },
  })
}

export function usePostTransaction() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: (id: number) =>
      transactionApi.postTransaction(tenant!.subdomain, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["transactions", tenant?.subdomain] })
      toast({
        title: "Success",
        description: "Transaction posted successfully",
      })
    },
  })
}

export function useUnpostTransaction() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: (id: number) =>
      transactionApi.unpostTransaction(tenant!.subdomain, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["transactions", tenant?.subdomain] })
      toast({
        title: "Success",
        description: "Transaction unposted successfully",
      })
    },
  })
}


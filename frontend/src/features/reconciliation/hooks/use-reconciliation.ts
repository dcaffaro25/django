import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useTenant } from "@/providers/TenantProvider"
import type {
  ReconciliationTask,
  ReconciliationConfig,
  ReconciliationPipeline,
  ReconciliationDashboard,
  PaginatedResponse,
} from "@/types"
import { useToast } from "@/components/ui/use-toast"
import * as reconciliationApi from "../api"

export function useReconciliationTasks(params?: Record<string, unknown>) {
  const { tenant } = useTenant()
  
  return useQuery({
    queryKey: ["reconciliation-tasks", tenant?.subdomain, params],
    queryFn: () => reconciliationApi.getReconciliationTasks(tenant!.subdomain, params),
    enabled: !!tenant,
  })
}

export function useReconciliationTask(id: number) {
  const { tenant } = useTenant()
  
  return useQuery({
    queryKey: ["reconciliation-task", tenant?.subdomain, id],
    queryFn: () => reconciliationApi.getReconciliationTask(tenant!.subdomain, id),
    enabled: !!tenant && !!id,
  })
}

export function useReconciliationDashboard() {
  const { tenant } = useTenant()
  
  return useQuery({
    queryKey: ["reconciliation-dashboard", tenant?.subdomain],
    queryFn: () => reconciliationApi.getReconciliationDashboard(tenant!.subdomain),
    enabled: !!tenant,
  })
}

export function useReconciliationConfigs(params?: Record<string, unknown>) {
  const { tenant } = useTenant()
  
  return useQuery({
    queryKey: ["reconciliation-configs", tenant?.subdomain, params],
    queryFn: () => reconciliationApi.getReconciliationConfigs(tenant!.subdomain, params),
    enabled: !!tenant,
  })
}

export function useCreateReconciliationConfig() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: (data: Partial<ReconciliationConfig>) =>
      reconciliationApi.createReconciliationConfig(tenant!.subdomain, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reconciliation-configs", tenant?.subdomain] })
      toast({
        title: "Success",
        description: "Reconciliation config created successfully",
      })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to create config",
        variant: "destructive",
      })
    },
  })
}

export function useStartReconciliation() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: (data: {
      config_id?: number
      pipeline_id?: number
      bank_ids?: number[]
      book_ids?: number[]
      auto_match_100?: boolean
    }) => reconciliationApi.startReconciliation(tenant!.subdomain, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reconciliation-tasks", tenant?.subdomain] })
      toast({
        title: "Success",
        description: "Reconciliation task started",
      })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to start task",
        variant: "destructive",
      })
    },
  })
}


// Settings feature hooks
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useTenant } from "@/providers/TenantProvider"
import type {
  IntegrationRule,
  SubstitutionRule,
  PaginatedResponse,
} from "@/types"
import { useToast } from "@/components/ui/use-toast"
import * as settingsApi from "../api"

// Integration Rules
export function useIntegrationRules(params?: Record<string, unknown>) {
  const { tenant } = useTenant()
  
  return useQuery({
    queryKey: ["integration-rules", tenant?.subdomain, params],
    queryFn: () => settingsApi.getIntegrationRules(tenant!.subdomain, params),
    enabled: !!tenant,
  })
}

export function useCreateIntegrationRule() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: (data: Partial<IntegrationRule>) =>
      settingsApi.createIntegrationRule(tenant!.subdomain, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["integration-rules", tenant?.subdomain] })
      toast({ title: "Success", description: "Integration rule created successfully" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to create rule",
        variant: "destructive",
      })
    },
  })
}

export function useUpdateIntegrationRule() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<IntegrationRule> }) =>
      settingsApi.updateIntegrationRule(tenant!.subdomain, id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["integration-rules", tenant?.subdomain] })
      toast({ title: "Success", description: "Integration rule updated successfully" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to update rule",
        variant: "destructive",
      })
    },
  })
}

export function useDeleteIntegrationRule() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: (id: number) => settingsApi.deleteIntegrationRule(tenant!.subdomain, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["integration-rules", tenant?.subdomain] })
      toast({ title: "Success", description: "Integration rule deleted successfully" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to delete rule",
        variant: "destructive",
      })
    },
  })
}

export function useValidateRule() {
  const { tenant } = useTenant()
  const { toast } = useToast()

  return useMutation({
    mutationFn: (data: {
      trigger_event: string
      rule: string
      filter_conditions?: string
      num_records?: number
    }) => settingsApi.validateRule(tenant!.subdomain, data),
    onError: (error: any) => {
      toast({
        title: "Validation Error",
        description: error.response?.data?.detail || error.message || "Rule validation failed",
        variant: "destructive",
      })
    },
  })
}

export function useTestRule() {
  const { tenant } = useTenant()
  const { toast } = useToast()

  return useMutation({
    mutationFn: (data: {
      setup_data: string
      payload: string
      rule: string
    }) => settingsApi.testRule(tenant!.subdomain, data),
    onError: (error: any) => {
      toast({
        title: "Test Error",
        description: error.response?.data?.detail || error.message || "Rule test failed",
        variant: "destructive",
      })
    },
  })
}

// Substitution Rules
export function useSubstitutionRules(params?: Record<string, unknown>) {
  const { tenant } = useTenant()
  
  return useQuery({
    queryKey: ["substitution-rules", tenant?.subdomain, params],
    queryFn: () => settingsApi.getSubstitutionRules(tenant!.subdomain, params),
    enabled: !!tenant,
  })
}

export function useCreateSubstitutionRule() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: (data: Partial<SubstitutionRule>) =>
      settingsApi.createSubstitutionRule(tenant!.subdomain, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["substitution-rules", tenant?.subdomain] })
      toast({ title: "Success", description: "Substitution rule created successfully" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to create rule",
        variant: "destructive",
      })
    },
  })
}

export function useUpdateSubstitutionRule() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<SubstitutionRule> }) =>
      settingsApi.updateSubstitutionRule(tenant!.subdomain, id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["substitution-rules", tenant?.subdomain] })
      toast({ title: "Success", description: "Substitution rule updated successfully" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to update rule",
        variant: "destructive",
      })
    },
  })
}

export function useDeleteSubstitutionRule() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: (id: number) => settingsApi.deleteSubstitutionRule(tenant!.subdomain, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["substitution-rules", tenant?.subdomain] })
      toast({ title: "Success", description: "Substitution rule deleted successfully" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to delete rule",
        variant: "destructive",
      })
    },
  })
}


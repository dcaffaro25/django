// HR feature hooks
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useTenant } from "@/providers/TenantProvider"
import type {
  Employee,
  Position,
  TimeTracking,
  Payroll,
  RecurringAdjustment,
  PaginatedResponse,
} from "@/types"
import { useToast } from "@/components/ui/use-toast"
import * as hrApi from "../api"

// Employees
export function useEmployees(params?: Record<string, unknown>) {
  const { tenant } = useTenant()
  
  return useQuery({
    queryKey: ["employees", tenant?.subdomain, params],
    queryFn: () => hrApi.getEmployees(tenant!.subdomain, params),
    enabled: !!tenant,
  })
}

export function useCreateEmployee() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: (data: Partial<Employee>) =>
      hrApi.createEmployee(tenant!.subdomain, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["employees", tenant?.subdomain] })
      toast({ title: "Success", description: "Employee created successfully" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to create employee",
        variant: "destructive",
      })
    },
  })
}

export function useUpdateEmployee() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<Employee> }) =>
      hrApi.updateEmployee(tenant!.subdomain, id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["employees", tenant?.subdomain] })
      toast({ title: "Success", description: "Employee updated successfully" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to update employee",
        variant: "destructive",
      })
    },
  })
}

export function useDeleteEmployee() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: (id: number) => hrApi.deleteEmployee(tenant!.subdomain, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["employees", tenant?.subdomain] })
      toast({ title: "Success", description: "Employee deleted successfully" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to delete employee",
        variant: "destructive",
      })
    },
  })
}

// Positions
export function usePositions(params?: Record<string, unknown>) {
  const { tenant } = useTenant()
  
  return useQuery({
    queryKey: ["positions", tenant?.subdomain, params],
    queryFn: () => hrApi.getPositions(tenant!.subdomain, params),
    enabled: !!tenant,
  })
}

export function useCreatePosition() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: (data: Partial<Position>) =>
      hrApi.createPosition(tenant!.subdomain, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["positions", tenant?.subdomain] })
      toast({ title: "Success", description: "Position created successfully" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to create position",
        variant: "destructive",
      })
    },
  })
}

export function useUpdatePosition() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<Position> }) =>
      hrApi.updatePosition(tenant!.subdomain, id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["positions", tenant?.subdomain] })
      toast({ title: "Success", description: "Position updated successfully" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to update position",
        variant: "destructive",
      })
    },
  })
}

export function useDeletePosition() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: (id: number) => hrApi.deletePosition(tenant!.subdomain, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["positions", tenant?.subdomain] })
      toast({ title: "Success", description: "Position deleted successfully" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to delete position",
        variant: "destructive",
      })
    },
  })
}

// Time Tracking
export function useTimeTracking(params?: Record<string, unknown>) {
  const { tenant } = useTenant()
  
  return useQuery({
    queryKey: ["time-tracking", tenant?.subdomain, params],
    queryFn: () => hrApi.getTimeTracking(tenant!.subdomain, params),
    enabled: !!tenant,
  })
}

export function useCreateTimeTracking() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: (data: Partial<TimeTracking>) =>
      hrApi.createTimeTracking(tenant!.subdomain, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["time-tracking", tenant?.subdomain] })
      toast({ title: "Success", description: "Time entry created successfully" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to create time entry",
        variant: "destructive",
      })
    },
  })
}

export function useApproveTimeTracking() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: (id: number) => hrApi.approveTimeTracking(tenant!.subdomain, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["time-tracking", tenant?.subdomain] })
      toast({ title: "Success", description: "Time entry approved" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to approve time entry",
        variant: "destructive",
      })
    },
  })
}

export function useRejectTimeTracking() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: (id: number) => hrApi.rejectTimeTracking(tenant!.subdomain, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["time-tracking", tenant?.subdomain] })
      toast({ title: "Success", description: "Time entry rejected" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to reject time entry",
        variant: "destructive",
      })
    },
  })
}

// Payrolls
export function usePayrolls(params?: Record<string, unknown>) {
  const { tenant } = useTenant()
  
  return useQuery({
    queryKey: ["payrolls", tenant?.subdomain, params],
    queryFn: () => hrApi.getPayrolls(tenant!.subdomain, params),
    enabled: !!tenant,
  })
}

export function useGenerateMonthlyPayroll() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: (data: { period_start: string; period_end: string }) =>
      hrApi.generateMonthlyPayroll(tenant!.subdomain, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["payrolls", tenant?.subdomain] })
      toast({ title: "Success", description: "Payroll generated successfully" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to generate payroll",
        variant: "destructive",
      })
    },
  })
}

export function useRecalculatePayroll() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: (id: number) => hrApi.recalculatePayroll(tenant!.subdomain, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["payrolls", tenant?.subdomain] })
      toast({ title: "Success", description: "Payroll recalculated successfully" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to recalculate payroll",
        variant: "destructive",
      })
    },
  })
}

// Recurring Adjustments
export function useRecurringAdjustments(params?: Record<string, unknown>) {
  const { tenant } = useTenant()
  
  return useQuery({
    queryKey: ["recurring-adjustments", tenant?.subdomain, params],
    queryFn: () => hrApi.getRecurringAdjustments(tenant!.subdomain, params),
    enabled: !!tenant,
  })
}

export function useCreateRecurringAdjustment() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: (data: Partial<RecurringAdjustment>) =>
      hrApi.createRecurringAdjustment(tenant!.subdomain, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["recurring-adjustments", tenant?.subdomain] })
      toast({ title: "Success", description: "Recurring adjustment created successfully" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to create adjustment",
        variant: "destructive",
      })
    },
  })
}

export function useUpdateRecurringAdjustment() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<RecurringAdjustment> }) =>
      hrApi.updateRecurringAdjustment(tenant!.subdomain, id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["recurring-adjustments", tenant?.subdomain] })
      toast({ title: "Success", description: "Recurring adjustment updated successfully" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to update adjustment",
        variant: "destructive",
      })
    },
  })
}

export function useDeleteRecurringAdjustment() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { tenant } = useTenant()

  return useMutation({
    mutationFn: (id: number) => hrApi.deleteRecurringAdjustment(tenant!.subdomain, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["recurring-adjustments", tenant?.subdomain] })
      toast({ title: "Success", description: "Recurring adjustment deleted successfully" })
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.detail || error.message || "Failed to delete adjustment",
        variant: "destructive",
      })
    },
  })
}


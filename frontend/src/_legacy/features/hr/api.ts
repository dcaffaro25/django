// HR API endpoints
import { apiClient } from "@/lib/api-client"
import type {
  Employee,
  Position,
  TimeTracking,
  Payroll,
  RecurringAdjustment,
  PaginatedResponse,
} from "@/types"

// Employees
export async function getEmployees(
  tenant: string,
  params?: Record<string, unknown>
): Promise<PaginatedResponse<Employee>> {
  return apiClient.get<PaginatedResponse<Employee>>("/api/hr/employees/", params)
}

export async function createEmployee(
  tenant: string,
  data: Partial<Employee>
): Promise<Employee> {
  return apiClient.post<Employee>("/api/hr/employees/", data)
}

export async function updateEmployee(
  tenant: string,
  id: number,
  data: Partial<Employee>
): Promise<Employee> {
  return apiClient.put<Employee>(`/api/hr/employees/${id}/`, data)
}

export async function deleteEmployee(tenant: string, id: number): Promise<void> {
  return apiClient.delete(`/api/hr/employees/${id}/`)
}

// Positions
export async function getPositions(
  tenant: string,
  params?: Record<string, unknown>
): Promise<PaginatedResponse<Position>> {
  return apiClient.get<PaginatedResponse<Position>>("/api/hr/positions/", params)
}

export async function createPosition(
  tenant: string,
  data: Partial<Position>
): Promise<Position> {
  return apiClient.post<Position>("/api/hr/positions/", data)
}

export async function updatePosition(
  tenant: string,
  id: number,
  data: Partial<Position>
): Promise<Position> {
  return apiClient.put<Position>(`/api/hr/positions/${id}/`, data)
}

export async function deletePosition(tenant: string, id: number): Promise<void> {
  return apiClient.delete(`/api/hr/positions/${id}/`)
}

// Time Tracking
export async function getTimeTracking(
  tenant: string,
  params?: Record<string, unknown>
): Promise<PaginatedResponse<TimeTracking>> {
  return apiClient.get<PaginatedResponse<TimeTracking>>("/api/hr/timetracking/", params)
}

export async function createTimeTracking(
  tenant: string,
  data: Partial<TimeTracking>
): Promise<TimeTracking> {
  return apiClient.post<TimeTracking>("/api/hr/timetracking/", data)
}

export async function updateTimeTracking(
  tenant: string,
  id: number,
  data: Partial<TimeTracking>
): Promise<TimeTracking> {
  return apiClient.put<TimeTracking>(`/api/hr/timetracking/${id}/`, data)
}

export async function approveTimeTracking(tenant: string, id: number): Promise<TimeTracking> {
  return apiClient.post<TimeTracking>(`/api/hr/timetracking/${id}/approve/`)
}

export async function rejectTimeTracking(tenant: string, id: number): Promise<TimeTracking> {
  return apiClient.post<TimeTracking>(`/api/hr/timetracking/${id}/reject/`)
}

// Payrolls
export async function getPayrolls(
  tenant: string,
  params?: Record<string, unknown>
): Promise<PaginatedResponse<Payroll>> {
  return apiClient.get<PaginatedResponse<Payroll>>("/api/hr/payrolls/", params)
}

export async function generateMonthlyPayroll(
  tenant: string,
  data: { period_start: string; period_end: string }
): Promise<Payroll[]> {
  return apiClient.post<Payroll[]>("/api/hr/payrolls/generate-monthly/", data)
}

export async function recalculatePayroll(tenant: string, id: number): Promise<Payroll> {
  return apiClient.post<Payroll>(`/api/hr/payrolls/recalculate/`, { payroll_id: id })
}

export async function deletePayroll(tenant: string, id: number): Promise<void> {
  return apiClient.delete(`/api/hr/payrolls/${id}/`)
}

// Recurring Adjustments
export async function getRecurringAdjustments(
  tenant: string,
  params?: Record<string, unknown>
): Promise<PaginatedResponse<RecurringAdjustment>> {
  return apiClient.get<PaginatedResponse<RecurringAdjustment>>(
    "/api/hr/recurring-adjustments/",
    params
  )
}

export async function createRecurringAdjustment(
  tenant: string,
  data: Partial<RecurringAdjustment>
): Promise<RecurringAdjustment> {
  return apiClient.post<RecurringAdjustment>("/api/hr/recurring-adjustments/", data)
}

export async function updateRecurringAdjustment(
  tenant: string,
  id: number,
  data: Partial<RecurringAdjustment>
): Promise<RecurringAdjustment> {
  return apiClient.put<RecurringAdjustment>(`/api/hr/recurring-adjustments/${id}/`, data)
}

export async function deleteRecurringAdjustment(tenant: string, id: number): Promise<void> {
  return apiClient.delete(`/api/hr/recurring-adjustments/${id}/`)
}


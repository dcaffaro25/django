import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { reportsApi, type AiGenerateTemplateRequest } from "./api"
import { useTenant } from "@/providers/TenantProvider"
import type {
  CalculateRequest,
  ReportTemplate,
  SaveRequest,
} from "./types"

const qk = {
  templates: (sub: string) => ["reports", sub, "templates"] as const,
  template: (sub: string, id: number) => ["reports", sub, "templates", id] as const,
  instances: (sub: string) => ["reports", sub, "instances"] as const,
  instance: (sub: string, id: number) => ["reports", sub, "instances", id] as const,
}

function useSub() {
  const { tenant } = useTenant()
  return tenant?.subdomain ?? ""
}

// --- Templates -------------------------------------------------------------

export function useReportTemplates(params?: { report_type?: string }) {
  const sub = useSub()
  return useQuery({
    queryKey: [...qk.templates(sub), params ?? null],
    queryFn: () => reportsApi.listTemplates(params),
    enabled: !!sub,
  })
}

export function useReportTemplate(id: number | null) {
  const sub = useSub()
  return useQuery({
    queryKey: id ? qk.template(sub, id) : ["reports", sub, "template", "none"],
    queryFn: () => reportsApi.getTemplate(id as number),
    enabled: !!sub && !!id,
  })
}

export function useSaveReportTemplate() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: ({ id, body }: { id?: number; body: ReportTemplate }) =>
      id ? reportsApi.updateTemplate(id, body) : reportsApi.createTemplate(body),
    onSuccess: (saved) => {
      qc.invalidateQueries({ queryKey: qk.templates(sub) })
      if (saved.id) qc.setQueryData(qk.template(sub, saved.id), saved)
    },
  })
}

export function useDeleteReportTemplate() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: (id: number) => reportsApi.deleteTemplate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.templates(sub) }),
  })
}

export function useDuplicateReportTemplate() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: (id: number) => reportsApi.duplicateTemplate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.templates(sub) }),
  })
}

// --- Calculate / Save ------------------------------------------------------

export function useCalculateReport() {
  return useMutation({
    mutationFn: (body: CalculateRequest) => reportsApi.calculate(body),
  })
}

export function useSaveReport() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: (body: SaveRequest) => reportsApi.save(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.instances(sub) }),
  })
}

// --- Instances -------------------------------------------------------------

export function useReportInstances(params?: {
  report_type?: string
  status?: string
  template?: number
}) {
  const sub = useSub()
  return useQuery({
    queryKey: [...qk.instances(sub), params ?? null],
    queryFn: () => reportsApi.listInstances(params),
    enabled: !!sub,
  })
}

export function useReportInstance(id: number | null) {
  const sub = useSub()
  return useQuery({
    queryKey: id ? qk.instance(sub, id) : ["reports", sub, "instance", "none"],
    queryFn: () => reportsApi.getInstance(id as number),
    enabled: !!sub && !!id,
  })
}

export function useDeleteReportInstance() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: (id: number) => reportsApi.deleteInstance(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.instances(sub) }),
  })
}

// --- AI --------------------------------------------------------------------

export function useAiGenerateTemplate() {
  return useMutation({
    mutationFn: (body: AiGenerateTemplateRequest) => reportsApi.aiGenerateTemplate(body),
  })
}

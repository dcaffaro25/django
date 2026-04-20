import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { statementsApi } from "./api"
import { useTenant } from "@/providers/TenantProvider"
import type {
  GenerateStatementInput,
  GeneratedStatement,
  PreviewStatementResponse,
  StatementTemplate,
} from "./types"

const qk = {
  templates: (sub: string) => ["statements", sub, "templates"] as const,
  template: (sub: string, id: number) => ["statements", sub, "templates", id] as const,
}

function useSub() {
  const { tenant } = useTenant()
  return tenant?.subdomain ?? ""
}

export function useTemplates(params?: { report_type?: string }) {
  const sub = useSub()
  return useQuery({
    queryKey: [...qk.templates(sub), params ?? null],
    queryFn: () => statementsApi.listTemplates(params),
    enabled: !!sub,
  })
}

export function useTemplate(id: number | null) {
  const sub = useSub()
  return useQuery({
    queryKey: id ? qk.template(sub, id) : ["statements", sub, "template", "none"],
    queryFn: () => statementsApi.getTemplate(id as number),
    enabled: !!sub && !!id,
  })
}

export function useSaveTemplate() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: ({ id, body }: { id?: number; body: StatementTemplate }) =>
      id ? statementsApi.updateTemplate(id, body) : statementsApi.createTemplate(body),
    onSuccess: (saved) => {
      qc.invalidateQueries({ queryKey: qk.templates(sub) })
      if (saved.id) qc.setQueryData(qk.template(sub, saved.id), saved)
    },
  })
}

export function useDeleteTemplate() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: (id: number) => statementsApi.deleteTemplate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.templates(sub) }),
  })
}

export function useDuplicateTemplate() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: (id: number) => statementsApi.duplicateTemplate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.templates(sub) }),
  })
}

export function useGenerateStatement() {
  return useMutation({
    mutationFn: (body: GenerateStatementInput) => statementsApi.generate(body),
  })
}

export type PreviewOrSaved = PreviewStatementResponse | GeneratedStatement

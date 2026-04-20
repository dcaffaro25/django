import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useTenant } from "@/providers/TenantProvider"
import {
  etlExecute,
  importTemplatesApi,
  nfeImport,
  ofxImport,
  substitutionRulesApi,
  type EtlExecuteParams,
} from "./api"
import type {
  ImportTransformationRule,
  SubstitutionRule,
} from "./types"

function useSub() {
  const { tenant } = useTenant()
  return tenant?.subdomain ?? ""
}

const qk = {
  substRules: (s: string) => ["imports", s, "substitution-rules"] as const,
  templates: (s: string) => ["imports", s, "templates"] as const,
}

export function useEtlExecute() {
  return useMutation({ mutationFn: (p: EtlExecuteParams) => etlExecute(p) })
}

export function useOfxImport() {
  return useMutation({ mutationFn: (files: File[]) => ofxImport(files) })
}

export function useNfeImport() {
  return useMutation({ mutationFn: (files: File[]) => nfeImport(files) })
}

export function useSubstitutionRules() {
  const sub = useSub()
  return useQuery({
    queryKey: qk.substRules(sub),
    queryFn: substitutionRulesApi.list,
    enabled: !!sub,
  })
}

export function useSaveSubstitutionRule() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: ({ id, body }: { id?: number; body: Partial<SubstitutionRule> }) =>
      id ? substitutionRulesApi.update(id, body) : substitutionRulesApi.create(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.substRules(sub) }),
  })
}

export function useDeleteSubstitutionRule() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: (id: number) => substitutionRulesApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.substRules(sub) }),
  })
}

export function useImportTemplates() {
  const sub = useSub()
  return useQuery({
    queryKey: qk.templates(sub),
    queryFn: importTemplatesApi.list,
    enabled: !!sub,
  })
}

export function useSaveImportTemplate() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: ({ id, body }: { id?: number; body: Partial<ImportTransformationRule> }) =>
      id ? importTemplatesApi.update(id, body) : importTemplatesApi.create(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.templates(sub) }),
  })
}

export function useDeleteImportTemplate() {
  const qc = useQueryClient()
  const sub = useSub()
  return useMutation({
    mutationFn: (id: number) => importTemplatesApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.templates(sub) }),
  })
}

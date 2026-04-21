import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useTenant } from "@/providers/TenantProvider"
import {
  bulkImport,
  etlExecute,
  etlPreview,
  nfeImport,
  ofxImport,
  ofxScan,
  substitutionRulesApi,
  type EtlExecuteParams,
} from "./api"
import type {
  SubstitutionRule,
} from "./types"

function useSub() {
  const { tenant } = useTenant()
  return tenant?.subdomain ?? ""
}

const qk = {
  substRules: (s: string) => ["imports", s, "substitution-rules"] as const,
}

export function useEtlExecute() {
  return useMutation({ mutationFn: (p: EtlExecuteParams) => etlExecute(p) })
}

/** Dry-run against /etl/preview — identical payload, backend rolls back. */
export function useEtlPreview() {
  return useMutation({ mutationFn: (p: EtlExecuteParams) => etlPreview(p) })
}

export function useOfxImport() {
  return useMutation({
    mutationFn: (args: { files: File[]; policy?: "records" | "files" }) =>
      ofxImport(args.files, args.policy),
  })
}

/** Scan-only against /import_ofx — reports duplicates without writing to DB. */
export function useOfxScan() {
  return useMutation({ mutationFn: (files: File[]) => ofxScan(files) })
}

export function useNfeImport() {
  return useMutation({
    mutationFn: (args: { files: File[]; dryRun?: boolean }) =>
      nfeImport(args.files, { dryRun: args.dryRun }),
  })
}

/**
 * Upload an Excel workbook to the master bulk-import endpoint. Pass
 * ``commit=false`` for a preview (backend wraps everything in a transaction
 * and rolls back) or ``commit=true`` to actually apply the changes.
 */
export function useBulkImport() {
  return useMutation({
    mutationFn: (args: { file: File; commit?: boolean }) =>
      bulkImport(args.file, { commit: args.commit }),
  })
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


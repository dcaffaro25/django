// ERP Integration sandbox types — matches erp_integrations.serializers.

export interface ERPConnection {
  id: number
  provider: number
  provider_display: string
  company: number
  name?: string | null
  app_key_masked?: string
  is_active: boolean
}

export type ParamLocation = "body" | "query" | "path" | "header"
export type ParamType =
  | "string" | "int" | "number" | "boolean" | "date" | "datetime"
  | "enum" | "object" | "array"

export interface ParamSpec {
  name: string
  type?: ParamType
  description?: string
  default?: unknown
  required?: boolean
  location?: ParamLocation
  options?: string[]
}

export type AuthStrategy =
  | "provider_default" | "query_params" | "bearer_header" | "basic" | "custom_template"

export type ApiDefinitionSource = "manual" | "imported" | "discovered"

export type TestOutcome = "" | "success" | "error" | "auth_fail"

export type PaginationMode = "none" | "page_number" | "cursor" | "offset"

export interface PaginationSpec {
  mode: PaginationMode
  page_param?: string
  page_size_param?: string
  page_size?: number
  cursor_path?: string
  next_cursor_param?: string
  offset_param?: string
  limit_param?: string
  max_pages?: number
}

export interface ERPAPIDefinition {
  id: number
  provider: number
  provider_display: string
  call: string
  url: string
  method: string
  param_schema: ParamSpec[]
  payload?: Record<string, unknown>
  transform_config?: Record<string, unknown> | null
  unique_id_config?: Record<string, unknown> | null
  description?: string | null
  is_active: boolean
  // Phase-1 metadata
  version: number
  source: ApiDefinitionSource
  documentation_url?: string | null
  last_tested_at?: string | null
  last_test_outcome: TestOutcome
  last_test_error?: string
  auth_strategy: AuthStrategy
  pagination_spec?: PaginationSpec | null
  records_path?: string
}

/** Body for POST /api-definitions/ (create) and PATCH /:id/ (update). */
export type ERPAPIDefinitionWrite = Partial<
  Omit<ERPAPIDefinition,
    "id" | "provider_display" | "payload" | "version"
    | "last_tested_at" | "last_test_outcome" | "last_test_error"
  >
> & {
  provider: number
  call: string
  url: string
  method?: string
}

export interface ApiDefinitionValidateResult {
  ok: boolean
  errors: Record<string, Array<string | { row?: number; field?: string; message?: string }>>
}

export interface InferredColumn {
  path: string
  type: string
  samples: unknown[]
}

export interface InferredShape {
  items_found: number
  columns: InferredColumn[]
}

export interface ApiDefinitionTestCallResult {
  ok: boolean
  outcome: TestOutcome
  error?: string | null
  diagnostics?: Record<string, unknown>
  preview_rows: Array<Record<string, unknown>>
  shape: InferredShape
  first_payload_redacted?: Record<string, unknown> | null
}

// ---- Phase 2: discovery ----

export type DiscoveryStrategy = "openapi" | "postman" | "html" | "llm"

export interface DiscoveryCandidate {
  call: string
  method: string
  url: string
  description: string
  param_schema: ParamSpec[]
  pagination_spec?: PaginationSpec | null
  records_path: string
  auth_strategy: AuthStrategy
  documentation_url: string
  confidence: number
  source_strategy: DiscoveryStrategy
  notes: string
}

export interface DiscoveryResult {
  url: string
  strategies_tried: DiscoveryStrategy[]
  strategy_used: DiscoveryStrategy | null
  candidates: DiscoveryCandidate[]
  errors: Array<{ strategy: string; message: string }>
}

export interface ImportDiscoveredResult {
  created: Array<{ id: number; call: string }>
  created_count: number
  failed: Array<{ index: number; call?: string; errors?: string[]; error?: string }>
  failed_count: number
}

export type SandboxBindingMode = "static" | "jmespath" | "fanout"

export interface SandboxBinding {
  mode: SandboxBindingMode
  into: string
  // static:
  value?: unknown
  // jmespath / fanout:
  source_step?: number
  expression?: string
}

export interface SandboxStep {
  order: number
  api_definition_id: number
  extra_params?: Record<string, unknown>
  param_bindings?: SandboxBinding[]
  select_fields?: string | null
}

export interface SandboxRequest {
  connection_id: number
  steps: SandboxStep[]
  max_steps?: number
  max_pages_per_step?: number
  max_fanout?: number
}

export interface SandboxStepDiagnostic {
  order: number
  api_call: string
  extracted: number
  stored: number
  skipped: number
  updated: number
  pages: number
  retries: number
  resolved_bindings?: Array<Record<string, unknown>>
  fanout?: { source_step: number; expression: string; into: string; value_count: number } | null
  invocations: Array<Record<string, unknown>>
  error?: string
}

export interface SandboxPreviewStep {
  order: number
  api_call: string
  row_count: number
  rows: Array<Record<string, unknown>>
  projected: unknown
}

export interface SandboxResult {
  success?: boolean
  status?: "completed" | "partial" | "failed"
  records_extracted?: number
  failed_step_order?: number | null
  errors?: string[]
  diagnostics?: {
    steps: SandboxStepDiagnostic[]
    retries: number
    pages: number
  }
  preview_by_step?: SandboxPreviewStep[]
  first_payload_redacted?: Record<string, unknown> | null
  caps?: { max_steps: number; max_pages_per_step: number; max_fanout: number }
  error?: string
}

export interface ERPSyncPipelineStepWrite {
  order: number
  api_definition: number
  extra_params?: Record<string, unknown>
  param_bindings?: SandboxBinding[]
  select_fields?: string | null
}

export interface ERPSyncPipelineWrite {
  connection: number
  name: string
  description?: string
  is_active?: boolean
  schedule_rrule?: string | null
  steps: ERPSyncPipelineStepWrite[]
}

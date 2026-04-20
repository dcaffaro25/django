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

export interface ERPAPIDefinition {
  id: number
  provider: number
  provider_display: string
  call: string
  url: string
  method: string
  param_schema: Array<{ name: string; type?: string; description?: string; default?: unknown; required?: boolean }>
  payload?: Record<string, unknown>
  unique_id_config?: Record<string, unknown> | null
  description?: string | null
  is_active: boolean
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

import { useState } from "react"
import { Sparkles, Loader2, CheckCircle2, AlertCircle, FileText, Settings2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { apiClient } from "@/lib/api-client"
import { cn } from "@/lib/utils"
import { useTenant } from "@/providers/TenantProvider"

interface DebugStep {
  step: number
  name: string
  status: "in_progress" | "completed" | "error"
}

interface DebugInfo {
  steps?: DebugStep[]
  prompt?: string
  system_prompt?: string
  company_context?: string
  accounts_context?: string
  existing_templates_context?: string
  ai_request_details?: {
    provider: string
    model: string
    prompt_length: number
    system_prompt_length: number
  }
}

interface SuggestionResult {
  status: string
  applied_changes?: boolean
  templates_created?: number
  templates_updated?: number
  lines_created?: number
  lines_updated?: number
  validation_warnings?: string[]
  ai_raw_response?: any
  debug_info?: DebugInfo
  error?: string
}

const AI_PROVIDERS = [
  { id: "openai", label: "OpenAI" },
  { id: "anthropic", label: "Anthropic" },
]

const AI_MODELS = {
  openai: [
    { id: "gpt-4o", label: "GPT-4o", description: "Most capable" },
    { id: "gpt-4o-mini", label: "GPT-4o Mini", description: "Fast & affordable" },
    { id: "gpt-4-turbo", label: "GPT-4 Turbo", description: "With vision" },
  ],
  anthropic: [
    { id: "claude-3-5-sonnet-20241022", label: "Claude 3.5 Sonnet", description: "Latest" },
    { id: "claude-3-opus-20240229", label: "Claude 3 Opus", description: "Most capable" },
  ],
}

export function AITemplateTestPage() {
  const { tenant } = useTenant()
  const [userPreferences, setUserPreferences] = useState("")
  const [aiProvider, setAiProvider] = useState("openai")
  const [aiModel, setAiModel] = useState("gpt-4o-mini")
  const [applyChanges, setApplyChanges] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [result, setResult] = useState<SuggestionResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault()

    if (!tenant) {
      setError("Please select a workspace/tenant first")
      return
    }

    setIsLoading(true)
    setError(null)
    setResult(null)

    try {
      const response = await apiClient.post<SuggestionResult>(
        `/api/financial-statement-templates/suggest_templates/`,
        {
          user_preferences: userPreferences || undefined,
          apply_changes: applyChanges,
          ai_provider: aiProvider,
          ai_model: aiModel,
        }
      )

      setResult(response)
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : "Failed to generate suggestions"
      setError(errorMessage)
      setResult({
        status: "error",
        error: errorMessage,
      })
    } finally {
      setIsLoading(false)
    }
  }

  // Update model when provider changes
  const handleProviderChange = (provider: string) => {
    setAiProvider(provider)
    const models = AI_MODELS[provider as keyof typeof AI_MODELS]
    if (models && models.length > 0) {
      setAiModel(models[0].id)
    }
  }

  return (
    <div className="flex flex-col min-h-[calc(100vh-4rem)] p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="flex items-center justify-center w-12 h-12 rounded-xl bg-primary/10">
          <Sparkles className="w-6 h-6 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold">AI Template Suggestion Test</h1>
          <p className="text-sm text-muted-foreground">
            Test AI-powered financial statement template generation
          </p>
        </div>
      </div>

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Input Panel */}
        <Card>
          <CardHeader>
            <CardTitle>Configuration</CardTitle>
            <CardDescription>
              Configure AI settings and preferences for template generation
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Tenant Info */}
            {tenant ? (
              <div className="p-3 bg-muted rounded-lg">
                <p className="text-sm font-medium">Workspace</p>
                <p className="text-sm text-muted-foreground">{tenant.name}</p>
              </div>
            ) : (
              <div className="p-3 bg-destructive/10 rounded-lg border border-destructive/20">
                <p className="text-sm text-destructive">
                  Please select a workspace from the sidebar
                </p>
              </div>
            )}

            {/* AI Provider */}
            <div className="space-y-2">
              <label className="text-sm font-medium">AI Provider</label>
              <Select value={aiProvider} onValueChange={handleProviderChange}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {AI_PROVIDERS.map((provider) => (
                    <SelectItem key={provider.id} value={provider.id}>
                      {provider.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* AI Model */}
            <div className="space-y-2">
              <label className="text-sm font-medium">AI Model</label>
              <Select value={aiModel} onValueChange={setAiModel}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {AI_MODELS[aiProvider as keyof typeof AI_MODELS]?.map((model) => (
                    <SelectItem key={model.id} value={model.id}>
                      <div className="flex items-center gap-2">
                        <span>{model.label}</span>
                        <span className="text-xs text-muted-foreground">({model.description})</span>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* User Preferences */}
            <div className="space-y-2">
              <label className="text-sm font-medium">User Preferences (Optional)</label>
              <Textarea
                value={userPreferences}
                onChange={(e) => setUserPreferences(e.target.value)}
                placeholder="e.g., I want revenue broken down to 3 levels, OPEX to 1 level..."
                className="min-h-[120px] resize-none"
              />
              <p className="text-xs text-muted-foreground">
                Describe how you want the templates structured
              </p>
            </div>

            {/* Apply Changes Toggle */}
            <div className="flex items-center space-x-2 p-3 bg-muted/50 rounded-lg">
              <input
                type="checkbox"
                id="apply-changes"
                checked={applyChanges}
                onChange={(e) => setApplyChanges(e.target.checked)}
                className="w-4 h-4 rounded border-gray-300"
              />
              <label htmlFor="apply-changes" className="text-sm font-medium cursor-pointer">
                Apply changes to database
              </label>
            </div>
            <p className="text-xs text-muted-foreground -mt-2">
              {applyChanges
                ? "⚠️ Templates will be created/updated in the database"
                : "✓ Preview mode - no changes will be saved"}
            </p>

            {/* Submit Button */}
            <div className="pt-2">
              <Button
                onClick={handleSubmit}
                disabled={isLoading || !tenant}
                className="w-full"
                size="lg"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Generating Suggestions...
                  </>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4 mr-2" />
                    Generate Template Suggestions
                  </>
                )}
              </Button>
              {!tenant && (
                <p className="text-xs text-muted-foreground mt-2 text-center">
                  Please select a workspace to enable this button
                </p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Results Panel */}
        <Card>
          <CardHeader>
            <CardTitle>Results</CardTitle>
            <CardDescription>AI-generated template suggestions and status</CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading && (
              <div className="flex flex-col items-center justify-center py-12">
                <Loader2 className="w-8 h-8 animate-spin text-primary mb-4" />
                <p className="text-sm text-muted-foreground">
                  AI is analyzing your chart of accounts and generating suggestions...
                </p>
              </div>
            )}

            {!isLoading && error && (
              <div className="p-4 bg-destructive/10 rounded-lg border border-destructive/20">
                <div className="flex items-start gap-3">
                  <AlertCircle className="w-5 h-5 text-destructive flex-shrink-0 mt-0.5" />
                  <div className="flex-1">
                    <p className="text-sm font-medium text-destructive">Error</p>
                    <p className="text-sm text-muted-foreground mt-1">{error}</p>
                  </div>
                </div>
              </div>
            )}

            {!isLoading && result && (
              <div className="space-y-4">
                {/* Status */}
                <div
                  className={cn(
                    "p-4 rounded-lg border",
                    result.status === "success"
                      ? "bg-green-50 border-green-200"
                      : result.status === "partial"
                      ? "bg-yellow-50 border-yellow-200"
                      : "bg-red-50 border-red-200"
                  )}
                >
                  <div className="flex items-center gap-2 mb-2">
                    {result.status === "success" ? (
                      <CheckCircle2 className="w-5 h-5 text-green-600" />
                    ) : (
                      <AlertCircle className="w-5 h-5 text-yellow-600" />
                    )}
                    <p className="font-medium capitalize">{result.status}</p>
                  </div>
                  {result.error && (
                    <p className="text-sm text-muted-foreground">{result.error}</p>
                  )}
                </div>

                {/* Statistics */}
                {(result.templates_created !== undefined ||
                  result.templates_updated !== undefined ||
                  result.lines_created !== undefined ||
                  result.lines_updated !== undefined) && (
                  <div className="grid grid-cols-2 gap-4">
                    {result.templates_created !== undefined && (
                      <div className="p-3 bg-muted rounded-lg">
                        <p className="text-xs text-muted-foreground">Templates Created</p>
                        <p className="text-2xl font-bold">{result.templates_created}</p>
                      </div>
                    )}
                    {result.templates_updated !== undefined && (
                      <div className="p-3 bg-muted rounded-lg">
                        <p className="text-xs text-muted-foreground">Templates Updated</p>
                        <p className="text-2xl font-bold">{result.templates_updated}</p>
                      </div>
                    )}
                    {result.lines_created !== undefined && (
                      <div className="p-3 bg-muted rounded-lg">
                        <p className="text-xs text-muted-foreground">Lines Created</p>
                        <p className="text-2xl font-bold">{result.lines_created}</p>
                      </div>
                    )}
                    {result.lines_updated !== undefined && (
                      <div className="p-3 bg-muted rounded-lg">
                        <p className="text-xs text-muted-foreground">Lines Updated</p>
                        <p className="text-2xl font-bold">{result.lines_updated}</p>
                      </div>
                    )}
                  </div>
                )}

                {/* Validation Warnings */}
                {result.validation_warnings && result.validation_warnings.length > 0 && (
                  <div className="p-4 bg-yellow-50 rounded-lg border border-yellow-200">
                    <p className="text-sm font-medium mb-2">Validation Warnings</p>
                    <ul className="list-disc list-inside space-y-1">
                      {result.validation_warnings.map((warning, idx) => (
                        <li key={idx} className="text-sm text-muted-foreground">
                          {warning}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Debug Information - Steps */}
                {result.debug_info?.steps && result.debug_info.steps.length > 0 && (
                  <div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
                    <p className="text-sm font-medium mb-3">Execution Steps</p>
                    <div className="space-y-2">
                      {result.debug_info.steps.map((step) => (
                        <div
                          key={step.step}
                          className={cn(
                            "flex items-center gap-2 text-sm",
                            step.status === "completed"
                              ? "text-green-700"
                              : step.status === "error"
                              ? "text-red-700"
                              : "text-blue-700"
                          )}
                        >
                          {step.status === "completed" ? (
                            <CheckCircle2 className="w-4 h-4" />
                          ) : step.status === "error" ? (
                            <AlertCircle className="w-4 h-4" />
                          ) : (
                            <Loader2 className="w-4 h-4 animate-spin" />
                          )}
                          <span>
                            Step {step.step}: {step.name}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Debug Information - AI Request Details */}
                {result.debug_info?.ai_request_details && (
                  <div className="p-4 bg-muted rounded-lg">
                    <p className="text-sm font-medium mb-2">AI Request Details</p>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div>
                        <span className="text-muted-foreground">Provider:</span>{" "}
                        <span className="font-medium">
                          {result.debug_info.ai_request_details.provider}
                        </span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Model:</span>{" "}
                        <span className="font-medium">
                          {result.debug_info.ai_request_details.model}
                        </span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Prompt Length:</span>{" "}
                        <span className="font-medium">
                          {result.debug_info.ai_request_details.prompt_length.toLocaleString()} chars
                        </span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">System Prompt Length:</span>{" "}
                        <span className="font-medium">
                          {result.debug_info.ai_request_details.system_prompt_length.toLocaleString()}{" "}
                          chars
                        </span>
                      </div>
                    </div>
                  </div>
                )}

                {/* Debug Information - Prompt */}
                {result.debug_info?.prompt && (
                  <details className="mt-4">
                    <summary className="cursor-pointer text-sm font-medium flex items-center gap-2">
                      <FileText className="w-4 h-4" />
                      View AI Prompt ({result.debug_info.prompt.length.toLocaleString()} chars)
                    </summary>
                    <div className="mt-2 p-4 bg-muted rounded-lg overflow-auto max-h-[400px]">
                      <pre className="text-xs whitespace-pre-wrap">
                        {result.debug_info.prompt}
                      </pre>
                    </div>
                  </details>
                )}

                {/* Debug Information - System Prompt */}
                {result.debug_info?.system_prompt && (
                  <details className="mt-2">
                    <summary className="cursor-pointer text-sm font-medium flex items-center gap-2">
                      <Settings2 className="w-4 h-4" />
                      View System Prompt ({result.debug_info.system_prompt.length.toLocaleString()}{" "}
                      chars)
                    </summary>
                    <div className="mt-2 p-4 bg-muted rounded-lg overflow-auto max-h-[300px]">
                      <pre className="text-xs whitespace-pre-wrap">
                        {result.debug_info.system_prompt}
                      </pre>
                    </div>
                  </details>
                )}

                {/* Debug Information - Context Sections */}
                {result.debug_info?.company_context && (
                  <details className="mt-2">
                    <summary className="cursor-pointer text-sm font-medium flex items-center gap-2">
                      <FileText className="w-4 h-4" />
                      View Company Context
                    </summary>
                    <div className="mt-2 p-4 bg-muted rounded-lg overflow-auto max-h-[300px]">
                      <pre className="text-xs whitespace-pre-wrap">
                        {result.debug_info.company_context}
                      </pre>
                    </div>
                  </details>
                )}

                {result.debug_info?.accounts_context && (
                  <details className="mt-2">
                    <summary className="cursor-pointer text-sm font-medium flex items-center gap-2">
                      <FileText className="w-4 h-4" />
                      View Accounts Context
                    </summary>
                    <div className="mt-2 p-4 bg-muted rounded-lg overflow-auto max-h-[300px]">
                      <pre className="text-xs whitespace-pre-wrap">
                        {result.debug_info.accounts_context}
                      </pre>
                    </div>
                  </details>
                )}

                {result.debug_info?.existing_templates_context && (
                  <details className="mt-2">
                    <summary className="cursor-pointer text-sm font-medium flex items-center gap-2">
                      <FileText className="w-4 h-4" />
                      View Existing Templates Context
                    </summary>
                    <div className="mt-2 p-4 bg-muted rounded-lg overflow-auto max-h-[300px]">
                      <pre className="text-xs whitespace-pre-wrap">
                        {result.debug_info.existing_templates_context}
                      </pre>
                    </div>
                  </details>
                )}

                {/* AI Raw Response */}
                {result.ai_raw_response && (
                  <details className="mt-4">
                    <summary className="cursor-pointer text-sm font-medium flex items-center gap-2">
                      <FileText className="w-4 h-4" />
                      View AI Raw Response
                    </summary>
                    <div className="mt-2 p-4 bg-muted rounded-lg overflow-auto max-h-[400px]">
                      <pre className="text-xs">
                        {JSON.stringify(result.ai_raw_response, null, 2)}
                      </pre>
                    </div>
                  </details>
                )}
              </div>
            )}

            {!isLoading && !result && !error && (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <Settings2 className="w-12 h-12 text-muted-foreground mb-4" />
                <p className="text-sm text-muted-foreground">
                  Configure settings and click &quot;Generate Template Suggestions&quot; to start
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}


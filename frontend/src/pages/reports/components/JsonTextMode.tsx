import { type ComponentType, lazy, Suspense, useEffect, useRef, useState } from "react"
import { Check, AlertCircle, Copy, ClipboardPaste, RotateCcw, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"
import type { TemplateDocument } from "@/features/reports"
import { TEMPLATE_DOCUMENT_JSON_SCHEMA } from "./document-json-schema"

// Lazy-load @monaco-editor/react — it pulls in ~3MB of monaco core, so we
// don't want it in the initial bundle. The Suspense fallback shows a
// spinner in the editor surface until the chunk arrives.
// The prop surface is typed loosely on purpose: pulling in monaco-editor's
// type package eagerly defeats the lazy-load. We only consume a handful of
// the editor's options below.
interface LazyMonacoProps {
  height?: string | number
  language?: string
  value?: string
  theme?: string
  onChange?: (value: string | undefined) => void
  onMount?: (editor: unknown, monaco: unknown) => void
  options?: Record<string, unknown>
}
const MonacoEditor = lazy<ComponentType<LazyMonacoProps>>(() =>
  import("@monaco-editor/react").then((m) => ({
    default: m.default as unknown as ComponentType<LazyMonacoProps>,
  })),
)

// Local type shim — we only use `languages.json.jsonDefaults.setDiagnosticsOptions`
// at runtime, pulled in via the editor's onMount callback. Keeping the type
// loose avoids importing monaco-editor's large type package eagerly.
type Monaco = {
  languages: {
    json: {
      jsonDefaults: {
        setDiagnosticsOptions: (opts: unknown) => void
      }
    }
  }
}

interface JsonEditStatus {
  kind: "idle" | "parsed" | "error"
  error?: string
}

/**
 * Text editor for the canonical document JSON. Monaco is configured with
 * our document schema so users get inline validation, completions, and
 * tooltips while editing. The commit path is a "Apply" button (not
 * live-write) so the visual editor doesn't thrash on every keystroke.
 */
export function JsonTextMode({
  document,
  onApply,
}: {
  document: TemplateDocument
  onApply: (next: TemplateDocument) => void
}) {
  const initialText = JSON.stringify(document, null, 2)
  const [text, setText] = useState(initialText)
  const [status, setStatus] = useState<JsonEditStatus>({ kind: "idle" })
  const lastDocRef = useRef<TemplateDocument>(document)

  // Sync back from props when the doc changes externally (AI edits, block
  // editor mutations, etc.) — only when the user isn't mid-edit of a dirty
  // text buffer that failed to parse.
  useEffect(() => {
    if (lastDocRef.current === document) return
    lastDocRef.current = document
    setText(JSON.stringify(document, null, 2))
    setStatus({ kind: "idle" })
  }, [document])

  const onMonacoMount = (_editor: unknown, monaco: unknown) => {
    const m = monaco as Monaco
    m.languages.json.jsonDefaults.setDiagnosticsOptions({
      validate: true,
      allowComments: false,
      schemas: [
        {
          uri: "memory://nord/template-document.schema.json",
          fileMatch: ["*"],
          schema: TEMPLATE_DOCUMENT_JSON_SCHEMA,
        },
      ],
    })
  }

  const tryParse = (raw: string): TemplateDocument | null => {
    try {
      return JSON.parse(raw) as TemplateDocument
    } catch {
      return null
    }
  }

  const apply = () => {
    const parsed = tryParse(text)
    if (!parsed) {
      setStatus({ kind: "error", error: "JSON inválido — verifique os erros destacados." })
      return
    }
    // Minimal shape check: the pydantic validator on the server is
    // authoritative, but we want to catch obvious issues before round-tripping.
    if (
      typeof parsed !== "object"
      || !parsed
      || typeof (parsed as TemplateDocument).name !== "string"
      || !Array.isArray((parsed as TemplateDocument).blocks)
    ) {
      setStatus({ kind: "error", error: "Estrutura inválida: name/report_type/blocks obrigatórios." })
      return
    }
    onApply(parsed as TemplateDocument)
    setStatus({ kind: "parsed" })
  }

  const reset = () => {
    setText(JSON.stringify(document, null, 2))
    setStatus({ kind: "idle" })
  }

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setStatus({ kind: "parsed" })
    } catch {
      /* clipboard unavailable — ignore */
    }
  }

  const paste = async () => {
    try {
      const clipboardText = await navigator.clipboard.readText()
      if (clipboardText) {
        setText(clipboardText)
        setStatus({ kind: "idle" })
      }
    } catch {
      /* ignore */
    }
  }

  const onChange = (val?: string) => {
    setText(val ?? "")
    setStatus({ kind: "idle" })
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2 text-[11px]">
        <button
          onClick={apply}
          className="inline-flex h-7 items-center gap-1 rounded-md bg-primary px-2 font-medium text-primary-foreground hover:bg-primary/90"
        >
          <Check className="h-3 w-3" /> Aplicar
        </button>
        <button
          onClick={reset}
          className="inline-flex h-7 items-center gap-1 rounded-md border border-border bg-background px-2 hover:bg-accent"
        >
          <RotateCcw className="h-3 w-3" /> Reverter
        </button>
        <button
          onClick={copy}
          className="inline-flex h-7 items-center gap-1 rounded-md border border-border bg-background px-2 hover:bg-accent"
        >
          <Copy className="h-3 w-3" /> Copiar
        </button>
        <button
          onClick={paste}
          className="inline-flex h-7 items-center gap-1 rounded-md border border-border bg-background px-2 hover:bg-accent"
        >
          <ClipboardPaste className="h-3 w-3" /> Colar
        </button>

        <div className="ml-auto flex items-center gap-1 text-[10px]">
          {status.kind === "parsed" && (
            <span className="inline-flex items-center gap-1 rounded-md bg-emerald-500/15 px-1.5 py-0.5 font-medium text-emerald-700 dark:text-emerald-400">
              <Check className="h-3 w-3" /> pronto
            </span>
          )}
          {status.kind === "error" && (
            <span
              className="inline-flex items-center gap-1 rounded-md bg-red-500/15 px-1.5 py-0.5 font-medium text-red-600"
              title={status.error}
            >
              <AlertCircle className="h-3 w-3" /> erro
            </span>
          )}
        </div>
      </div>

      {status.kind === "error" && status.error && (
        <div className="rounded-md border border-red-500/30 bg-red-500/5 p-2 text-[11px] text-red-700 dark:text-red-300">
          {status.error}
        </div>
      )}

      <div className={cn("rounded-md border border-border bg-background")}>
        <Suspense
          fallback={
            <div className="flex h-[480px] items-center justify-center gap-2 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span className="text-[12px]">Carregando editor...</span>
            </div>
          }
        >
          <MonacoEditor
            height="480px"
            language="json"
            value={text}
            onChange={onChange}
            onMount={onMonacoMount}
            theme="vs-dark"
            options={{
              fontSize: 12,
              minimap: { enabled: false },
              scrollBeyondLastLine: false,
              tabSize: 2,
              lineNumbers: "on",
              formatOnPaste: true,
              automaticLayout: true,
              wordWrap: "on",
            }}
          />
        </Suspense>
      </div>

      <p className="text-[10px] text-muted-foreground">
        Edite diretamente o documento JSON. Cole a saída da IA aqui para
        importar modelos externos. As alterações só entram no editor visual
        depois de clicar em Aplicar.
      </p>
    </div>
  )
}

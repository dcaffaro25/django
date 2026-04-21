/**
 * Canonical taxonomy of application "areas" for activity tracking.
 *
 * The backend uses the ``area`` string as a dimension in
 * :class:`core.models.UserActivityEvent` indexes, so keep the ids
 * **stable**. Changing an id mid-flight orphans historical data.
 *
 * Resolution rule: longest-prefix match. ``/reports/view/42`` resolves
 * via ``/reports/view`` (``reports.view``) before ``/reports``.
 */

export interface Area {
  /** Stable id. ``group.leaf`` convention; matches the sidebar grouping. */
  id: string
  /** Operator-facing label. pt-BR. */
  label: string
  /** Sidebar group ("Conciliação", "Contabilidade", …). */
  group: string
  /** Route prefix used for matching. */
  prefix: string
}

/**
 * List is iterated top-to-bottom with a longest-prefix check, so
 * keep the more specific entries before their parents. The route
 * strings are literal prefixes — no regex.
 */
export const AREAS: readonly Area[] = [
  // Reconciliation
  { id: "recon.workbench",      label: "Bancada",                 group: "Conciliação",   prefix: "/recon/workbench" },
  { id: "recon.reconciliations",label: "Conciliações",            group: "Conciliação",   prefix: "/recon/matches" },
  { id: "recon.tasks",          label: "Execuções",               group: "Conciliação",   prefix: "/recon/tasks" },
  { id: "recon.suggestions",    label: "Sugestões",               group: "Conciliação",   prefix: "/recon/suggestions" },
  { id: "recon.configs",        label: "Configurações",           group: "Conciliação",   prefix: "/recon/configs" },
  { id: "recon.pipelines",      label: "Pipelines",               group: "Conciliação",   prefix: "/recon/pipelines" },
  { id: "recon.embeddings",     label: "Embeddings",              group: "Conciliação",   prefix: "/recon/embeddings" },
  { id: "recon.balances",       label: "Saldos",                  group: "Conciliação",   prefix: "/recon/balances" },
  { id: "recon.dashboard",      label: "Painel de conciliação",   group: "Conciliação",   prefix: "/recon" },

  // Accounting
  { id: "accounting.bank_accounts",   label: "Contas bancárias",    group: "Contabilidade", prefix: "/accounting/bank-accounts" },
  { id: "accounting.bank_transactions", label: "Extratos bancários", group: "Contabilidade", prefix: "/accounting/bank-transactions" },
  { id: "accounting.transactions",    label: "Transações",          group: "Contabilidade", prefix: "/accounting/transactions" },
  { id: "accounting.journal_entries", label: "Lançamentos",         group: "Contabilidade", prefix: "/accounting/journal-entries" },
  { id: "accounting.accounts",        label: "Plano de contas",     group: "Contabilidade", prefix: "/accounting/accounts" },

  // Financial statements
  { id: "statements.templates",       label: "Modelos",             group: "Demonstrativos", prefix: "/statements/templates" },
  { id: "statements.builder",         label: "DREs e balanços",     group: "Demonstrativos", prefix: "/statements" },
  { id: "reports.view",               label: "Histórico (view)",    group: "Demonstrativos", prefix: "/reports/view" },
  { id: "reports.history",            label: "Histórico",           group: "Demonstrativos", prefix: "/reports/history" },
  { id: "reports.build",              label: "Novo demonstrativo",  group: "Demonstrativos", prefix: "/reports/build" },
  { id: "reports.builder_root",       label: "Demonstrativos (beta)", group: "Demonstrativos", prefix: "/reports" },

  // Settings & misc
  { id: "settings.ai_usage",          label: "Uso da IA",           group: "Outros",        prefix: "/settings/ai-usage" },
  { id: "settings.entities",          label: "Entidades",           group: "Outros",        prefix: "/settings/entities" },
  { id: "settings.root",              label: "Ajustes",             group: "Outros",        prefix: "/settings" },
  { id: "integrations.sandbox",       label: "Sandbox de API",      group: "Integrações",   prefix: "/integrations/sandbox" },
  { id: "integrations.root",          label: "Integrações",         group: "Integrações",   prefix: "/integrations" },
  { id: "billing",                    label: "Faturamento",         group: "Outros",        prefix: "/billing" },
  { id: "hr",                         label: "RH",                  group: "Outros",        prefix: "/hr" },
  { id: "inventory",                  label: "Estoque",             group: "Outros",        prefix: "/inventory" },

  // Imports
  { id: "imports.templates",          label: "Templates",           group: "Importações",   prefix: "/imports/templates" },
  { id: "imports.substitutions",      label: "Substituições",       group: "Importações",   prefix: "/imports/substitutions" },
  { id: "imports.hub",                label: "Importar arquivos",   group: "Importações",   prefix: "/imports" },

  // Admin
  { id: "admin.users",                label: "Administração · Usuários", group: "Administração", prefix: "/admin/users" },
  { id: "admin.activity",             label: "Administração · Atividade", group: "Administração", prefix: "/admin/activity" },
  { id: "admin.home",                 label: "Administração",       group: "Administração", prefix: "/admin" },

  // Fallback
  { id: "auth.login",                 label: "Login",               group: "Auth",          prefix: "/login" },
] as const

/**
 * Normalise a pathname: strip querystring, trailing slash, numeric
 * path segments (``/reports/view/42`` → ``/reports/view/:id``). The
 * canonical stored path is the normalised form so heatmaps don't
 * double-count.
 */
export function normalizePath(rawPath: string): string {
  const noQuery = rawPath.split("?")[0]!.split("#")[0]!
  const trimmed = noQuery.length > 1 && noQuery.endsWith("/") ? noQuery.slice(0, -1) : noQuery
  // Replace any segment that's purely digits (common for /:id). We
  // keep UUIDs as-is — they're rarer and useful for drill-downs.
  return trimmed
    .split("/")
    .map((seg) => (/^\d+$/.test(seg) ? ":id" : seg))
    .join("/")
}

/**
 * Longest-prefix match against AREAS. Returns ``null`` for paths
 * that don't match any known area — the caller decides whether to
 * send a beacon with ``area=""`` or drop it.
 */
export function resolveArea(rawPath: string): Area | null {
  const normalized = normalizePath(rawPath)
  let best: Area | null = null
  for (const a of AREAS) {
    if (normalized === a.prefix || normalized.startsWith(a.prefix + "/")) {
      if (!best || a.prefix.length > best.prefix.length) best = a
    }
  }
  return best
}

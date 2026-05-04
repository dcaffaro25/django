import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"
import { AppShell } from "@/components/layout/AppShell"
import { useAuth } from "@/providers/AuthProvider"
import { LoginPage } from "@/pages/auth/LoginPage"
import { DashboardPage } from "@/pages/recon/DashboardPage"
import { TasksPage } from "@/pages/recon/TasksPage"
import { WorkbenchPage } from "@/pages/recon/WorkbenchPage"
import { ReconciliationsPage } from "@/pages/recon/ReconciliationsPage"
import { SuggestionsLegacyRedirect } from "@/pages/recon/SuggestionsLegacyRedirect"
import { ConfigsPage } from "@/pages/recon/ConfigsPage"
import { PipelinesPage } from "@/pages/recon/PipelinesPage"
import { EmbeddingsPage } from "@/pages/recon/EmbeddingsPage"
import { ReconHubPage } from "@/pages/recon/ReconHubPage"
import { BankAccountsPage } from "@/pages/accounting/BankAccountsPage"
import { BankAccountDetailPage } from "@/pages/accounting/BankAccountDetailPage"
import { ChartOfAccountsPage } from "@/pages/accounting/ChartOfAccountsPage"
import { TransactionsPage } from "@/pages/accounting/TransactionsPage"
import { JournalEntriesPage } from "@/pages/accounting/JournalEntriesPage"
import { AccountingHubPage } from "@/pages/accounting/AccountingHubPage"
import { EntitiesPage } from "@/pages/settings/EntitiesPage"
import { TenantConfigPage } from "@/pages/settings/TenantConfigPage"
import { ApiSandboxPage } from "@/pages/integrations/ApiSandboxPage"
import { ApiDefinitionsPage } from "@/pages/integrations/ApiDefinitionsPage"
import { ApiDiscoveryPage } from "@/pages/integrations/ApiDiscoveryPage"
import { PipelineRoutinesPage } from "@/pages/integrations/PipelineRoutinesPage"
import { ImportsHubPage } from "@/pages/imports/ImportsHubPage"
import { ImportsHubWrapper } from "@/pages/imports/ImportsHubWrapper"
import { SubstitutionRulesPage } from "@/pages/imports/SubstitutionRulesPage"
import { ImportTemplatesPage } from "@/pages/imports/ImportTemplatesPage"
import { PlaceholderPage } from "@/pages/recon/PlaceholderPage"
import { ReportBuilderPage } from "@/pages/statements/ReportBuilderPage"
import { BuilderPage as ReportsBuilderPage } from "@/pages/reports/BuilderPage"
import { HistoryPage as ReportsHistoryPage } from "@/pages/reports/HistoryPage"
import { ViewPage as ReportsViewPage } from "@/pages/reports/ViewPage"
import {
  StandardReportsPage, DreTab, BalancoTab, DfcTab, CustomReportsTab,
} from "@/pages/reports/StandardReportsPage"
import { AiUsagePage } from "@/pages/settings/AiUsagePage"
import { BillingHubPage } from "@/pages/billing/BillingHubPage"
import { InvoicesPage } from "@/pages/billing/InvoicesPage"
import { NotasFiscaisPage } from "@/pages/billing/NotasFiscaisPage"
import { NfLinkReviewPage } from "@/pages/billing/NfLinkReviewPage"
import { BillingSettingsPage } from "@/pages/billing/BillingSettingsPage"
import { BusinessPartnersPage } from "@/pages/billing/BusinessPartnersPage"
import { ProductServicesPage } from "@/pages/billing/ProductServicesPage"
import { GroupsPage } from "@/pages/billing/GroupsPage"
import { DsoReportPage } from "@/pages/billing/DsoReportPage"
import { DataHealthPage } from "@/pages/billing/DataHealthPage"
import { AdminHomePage } from "@/pages/admin/AdminHomePage"
import { UsersPage as AdminUsersPage } from "@/pages/admin/UsersPage"
import { RuntimePage as AdminRuntimePage } from "@/pages/admin/RuntimePage"
import { AgentAuditPage } from "@/pages/admin/AgentAuditPage"
import { PedidoVendasReportPage } from "@/pages/erp/PedidoVendasReportPage"
import { SuperuserGuard } from "@/pages/admin/SuperuserGuard"
import { ActivityHeatmapPage } from "@/pages/admin/activity/ActivityHeatmapPage"
import { ActivityUserDetailPage } from "@/pages/admin/activity/ActivityUserDetailPage"
import { ActivityAreaDetailPage } from "@/pages/admin/activity/ActivityAreaDetailPage"
import { ActivityFunnelsPage } from "@/pages/admin/activity/ActivityFunnelsPage"
import { ActivityFrictionPage } from "@/pages/admin/activity/ActivityFrictionPage"
import { ErrorsPage as AdminErrorsPage } from "@/pages/admin/activity/ErrorsPage"
import { AgentConnectionPage } from "@/pages/admin/AgentConnectionPage"

function Protected({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth()
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/*"
          element={
            <Protected>
              <AppShell>
                <Routes>
                  <Route path="/" element={<Navigate to="/recon" replace />} />

                  {/* Conciliação hub. Same nine sub-pages as before --
                      they now render inside ``ReconHubPage`` which adds
                      a tab strip above them. The single sidebar link
                      points to ``/recon``. */}
                  <Route path="/recon" element={<ReconHubPage />}>
                    <Route index element={<DashboardPage />} />
                    <Route path="tasks" element={<TasksPage />} />
                    <Route path="workbench" element={<WorkbenchPage />} />
                    <Route path="matches" element={<ReconciliationsPage />} />
                    {/* Sugestões is merged into Execuções — preserve old
                        bookmarks by redirecting `/recon/suggestions` (and
                        `?task_id=X`) to the new combined page. */}
                    <Route path="suggestions" element={<SuggestionsLegacyRedirect />} />
                    <Route path="configs" element={<ConfigsPage />} />
                    <Route path="pipelines" element={<PipelinesPage />} />
                    <Route path="embeddings" element={<EmbeddingsPage />} />
                    <Route path="balances" element={<PlaceholderPage title="Saldos" subtitle="Banco vs. livro" />} />
                  </Route>

                  {/* Contabilidade hub. */}
                  <Route path="/accounting" element={<AccountingHubPage />}>
                    <Route index element={<Navigate to="/accounting/accounts" replace />} />
                    <Route path="bank-accounts" element={<BankAccountsPage />} />
                    <Route path="accounts" element={<ChartOfAccountsPage />} />
                    <Route path="transactions" element={<TransactionsPage />} />
                    <Route path="journal-entries" element={<JournalEntriesPage />} />
                  </Route>
                  {/* Per-account detail page lives outside the hub --
                      it's a deep link from the bank-accounts table and
                      shouldn't render the hub tabs above it. */}
                  <Route path="/accounting/bank-accounts/:id" element={<BankAccountDetailPage />} />

                  {/* Demonstrativos hub: standard tabs (DRE / Balanço /
                      DFC / Personalizados / Histórico) plus the legacy
                      builder + view at /reports/build and /reports/view/:id
                      which DON'T render under the tabbed shell. */}
                  <Route path="/reports" element={<StandardReportsPage />}>
                    <Route index element={<DreTab />} />
                    <Route path="balanco" element={<BalancoTab />} />
                    <Route path="dfc" element={<DfcTab />} />
                    <Route path="custom" element={<CustomReportsTab />} />
                    <Route path="history" element={<ReportsHistoryPage />} />
                  </Route>
                  <Route path="/reports/build" element={<ReportsBuilderPage />} />
                  <Route path="/reports/view/:id" element={<ReportsViewPage />} />

                  {/* Legacy demonstratives builder. */}
                  <Route path="/statements" element={<ReportBuilderPage />} />
                  <Route path="/statements/templates" element={<ReportBuilderPage />} />
                  <Route path="/statements/*" element={<PlaceholderPage title="Demonstrativos" />} />

                  {/* Settings */}
                  <Route path="/settings/ai-usage" element={<AiUsagePage />} />
                  <Route path="/settings/tenant" element={<TenantConfigPage />} />
                  <Route path="/settings/entities" element={<EntitiesPage />} />
                  <Route path="/settings/*" element={<PlaceholderPage title="Ajustes" />} />

                  <Route path="/billing" element={<BillingHubPage />}>
                    <Route index element={<InvoicesPage />} />
                    <Route path="nfe" element={<NotasFiscaisPage />} />
                    <Route path="parceiros" element={<BusinessPartnersPage />} />
                    <Route path="produtos" element={<ProductServicesPage />} />
                    <Route path="links" element={<NfLinkReviewPage />} />
                    <Route path="grupos" element={<GroupsPage />} />
                    <Route path="dso" element={<DsoReportPage />} />
                    <Route path="saude" element={<DataHealthPage />} />
                    <Route path="settings" element={<BillingSettingsPage />} />
                  </Route>
                  {/* Operação meta-tools. Saúde dos Dados is cross-domain
                      (covers accounting + billing + recon pipeline gaps),
                      so it lives here rather than under /billing. The
                      /billing/saude route above stays as an alias so any
                      existing bookmarks / CTA URLs keep working. */}
                  <Route path="/operacao/saude" element={<DataHealthPage />} />
                  <Route path="/hr/*" element={<PlaceholderPage title="RH" />} />
                  <Route path="/inventory/*" element={<PlaceholderPage title="Estoque" />} />
                  <Route path="/integrations/sandbox" element={<ApiSandboxPage />} />
                  {/* Phase-1 do plano Sandbox API: catálogo estruturado das
                      definições de API. O sandbox e as rotinas (futuras)
                      consomem o que é cadastrado aqui. */}
                  <Route path="/integrations/api-definitions" element={<ApiDefinitionsPage />} />
                  {/* Phase-2: descoberta de APIs a partir de URL de docs. */}
                  <Route path="/integrations/api-definitions/discover" element={<ApiDiscoveryPage />} />
                  {/* Phase-4: rotinas agendadas. */}
                  <Route path="/integrations/rotinas" element={<PipelineRoutinesPage />} />
                  <Route path="/integrations/*" element={<PlaceholderPage title="Integrações" />} />

                  {/* ERP — Omie reports powered by ApiPipeline snapshots. */}
                  <Route path="/erp/pedidos" element={<PedidoVendasReportPage />} />

                  {/* Importações hub. */}
                  <Route path="/imports" element={<ImportsHubWrapper />}>
                    <Route index element={<ImportsHubPage />} />
                    <Route path="templates" element={<ImportTemplatesPage />} />
                    <Route path="substitutions" element={<SubstitutionRulesPage />} />
                  </Route>
                  {/* Platform-admin area. SuperuserGuard renders a 403-ish
                      screen for non-superusers; the backend independently
                      enforces IsSuperUser on every /api/admin/* endpoint. */}
                  <Route path="/admin" element={<SuperuserGuard><AdminHomePage /></SuperuserGuard>} />
                  <Route path="/admin/users" element={<SuperuserGuard><AdminUsersPage /></SuperuserGuard>} />
                  <Route path="/admin/activity" element={<SuperuserGuard><ActivityHeatmapPage /></SuperuserGuard>} />
                  <Route path="/admin/activity/funnels" element={<SuperuserGuard><ActivityFunnelsPage /></SuperuserGuard>} />
                  <Route path="/admin/activity/friction" element={<SuperuserGuard><ActivityFrictionPage /></SuperuserGuard>} />
                  <Route path="/admin/activity/errors" element={<SuperuserGuard><AdminErrorsPage /></SuperuserGuard>} />
                  <Route path="/admin/activity/users/:id" element={<SuperuserGuard><ActivityUserDetailPage /></SuperuserGuard>} />
                  <Route path="/admin/activity/areas/:id" element={<SuperuserGuard><ActivityAreaDetailPage /></SuperuserGuard>} />
                  <Route path="/admin/runtime" element={<SuperuserGuard><AdminRuntimePage /></SuperuserGuard>} />
                  <Route path="/admin/agent" element={<SuperuserGuard><AgentConnectionPage /></SuperuserGuard>} />
                  <Route path="/admin/agent/audit" element={<SuperuserGuard><AgentAuditPage /></SuperuserGuard>} />
                  <Route path="/admin/*" element={<SuperuserGuard><AdminHomePage /></SuperuserGuard>} />
                  <Route path="*" element={<Navigate to="/recon" replace />} />
                </Routes>
              </AppShell>
            </Protected>
          }
        />
      </Routes>
    </BrowserRouter>
  )
}

import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"
import { AppShell } from "@/components/layout/AppShell"
import { useAuth } from "@/providers/AuthProvider"
import { LoginPage } from "@/pages/auth/LoginPage"
import { DashboardPage } from "@/pages/recon/DashboardPage"
import { TasksPage } from "@/pages/recon/TasksPage"
import { WorkbenchPage } from "@/pages/recon/WorkbenchPage"
import { ReconciliationsPage } from "@/pages/recon/ReconciliationsPage"
import { SuggestionsPage } from "@/pages/recon/SuggestionsPage"
import { ConfigsPage } from "@/pages/recon/ConfigsPage"
import { PipelinesPage } from "@/pages/recon/PipelinesPage"
import { EmbeddingsPage } from "@/pages/recon/EmbeddingsPage"
import { BankAccountsPage } from "@/pages/accounting/BankAccountsPage"
import { ChartOfAccountsPage } from "@/pages/accounting/ChartOfAccountsPage"
import { TransactionsPage } from "@/pages/accounting/TransactionsPage"
import { JournalEntriesPage } from "@/pages/accounting/JournalEntriesPage"
import { EntitiesPage } from "@/pages/settings/EntitiesPage"
import { ApiSandboxPage } from "@/pages/integrations/ApiSandboxPage"
import { ImportsHubPage } from "@/pages/imports/ImportsHubPage"
import { SubstitutionRulesPage } from "@/pages/imports/SubstitutionRulesPage"
import { ImportTemplatesPage } from "@/pages/imports/ImportTemplatesPage"
import { PlaceholderPage } from "@/pages/recon/PlaceholderPage"
import { ReportBuilderPage } from "@/pages/statements/ReportBuilderPage"
import { BuilderPage as ReportsBuilderPage } from "@/pages/reports/BuilderPage"
import { HistoryPage as ReportsHistoryPage } from "@/pages/reports/HistoryPage"
import { ViewPage as ReportsViewPage } from "@/pages/reports/ViewPage"
import { AiUsagePage } from "@/pages/settings/AiUsagePage"
import { AdminHomePage } from "@/pages/admin/AdminHomePage"
import { UsersPage as AdminUsersPage } from "@/pages/admin/UsersPage"
import { SuperuserGuard } from "@/pages/admin/SuperuserGuard"
import { ActivityHeatmapPage } from "@/pages/admin/activity/ActivityHeatmapPage"
import { ActivityUserDetailPage } from "@/pages/admin/activity/ActivityUserDetailPage"
import { ActivityAreaDetailPage } from "@/pages/admin/activity/ActivityAreaDetailPage"
import { ActivityFunnelsPage } from "@/pages/admin/activity/ActivityFunnelsPage"
import { ActivityFrictionPage } from "@/pages/admin/activity/ActivityFrictionPage"

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
                  <Route path="/recon" element={<DashboardPage />} />
                  <Route path="/recon/tasks" element={<TasksPage />} />
                  <Route path="/recon/workbench" element={<WorkbenchPage />} />
                  <Route path="/recon/matches" element={<ReconciliationsPage />} />
                  <Route path="/recon/suggestions" element={<SuggestionsPage />} />
                  <Route path="/recon/configs" element={<ConfigsPage />} />
                  <Route path="/recon/pipelines" element={<PipelinesPage />} />
                  <Route path="/recon/embeddings" element={<EmbeddingsPage />} />
                  <Route path="/recon/balances" element={<PlaceholderPage title="Saldos" subtitle="Banco vs. livro" />} />
                  <Route path="/accounting/bank-accounts" element={<BankAccountsPage />} />
                  <Route path="/accounting/accounts" element={<ChartOfAccountsPage />} />
                  <Route path="/accounting/transactions" element={<TransactionsPage />} />
                  <Route path="/accounting/journal-entries" element={<JournalEntriesPage />} />
                  <Route path="/accounting/*" element={<PlaceholderPage title="Contabilidade" />} />
                  <Route path="/statements" element={<ReportBuilderPage />} />
                  <Route path="/statements/templates" element={<ReportBuilderPage />} />
                  <Route path="/statements/*" element={<PlaceholderPage title="Demonstrativos" />} />
                  <Route path="/reports" element={<ReportsBuilderPage />} />
                  <Route path="/reports/build" element={<ReportsBuilderPage />} />
                  <Route path="/reports/history" element={<ReportsHistoryPage />} />
                  <Route path="/reports/view/:id" element={<ReportsViewPage />} />
                  <Route path="/settings/ai-usage" element={<AiUsagePage />} />
                  <Route path="/billing/*" element={<PlaceholderPage title="Faturamento" />} />
                  <Route path="/hr/*" element={<PlaceholderPage title="RH" />} />
                  <Route path="/inventory/*" element={<PlaceholderPage title="Estoque" />} />
                  <Route path="/integrations/sandbox" element={<ApiSandboxPage />} />
                  <Route path="/integrations/*" element={<PlaceholderPage title="Integrações" />} />
                  <Route path="/imports" element={<ImportsHubPage />} />
                  <Route path="/imports/templates" element={<ImportTemplatesPage />} />
                  <Route path="/imports/substitutions" element={<SubstitutionRulesPage />} />
                  <Route path="/imports/*" element={<ImportsHubPage />} />
                  <Route path="/settings/entities" element={<EntitiesPage />} />
                  <Route path="/settings/*" element={<PlaceholderPage title="Ajustes" />} />
                  {/* Platform-admin area. SuperuserGuard renders a 403-ish
                      screen for non-superusers; the backend independently
                      enforces IsSuperUser on every /api/admin/* endpoint. */}
                  <Route path="/admin" element={<SuperuserGuard><AdminHomePage /></SuperuserGuard>} />
                  <Route path="/admin/users" element={<SuperuserGuard><AdminUsersPage /></SuperuserGuard>} />
                  <Route path="/admin/activity" element={<SuperuserGuard><ActivityHeatmapPage /></SuperuserGuard>} />
                  <Route path="/admin/activity/funnels" element={<SuperuserGuard><ActivityFunnelsPage /></SuperuserGuard>} />
                  <Route path="/admin/activity/friction" element={<SuperuserGuard><ActivityFrictionPage /></SuperuserGuard>} />
                  <Route path="/admin/activity/users/:id" element={<SuperuserGuard><ActivityUserDetailPage /></SuperuserGuard>} />
                  <Route path="/admin/activity/areas/:id" element={<SuperuserGuard><ActivityAreaDetailPage /></SuperuserGuard>} />
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

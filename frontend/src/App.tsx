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
import { PlaceholderPage } from "@/pages/recon/PlaceholderPage"

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
                  <Route path="/statements/*" element={<PlaceholderPage title="Demonstrativos" />} />
                  <Route path="/billing/*" element={<PlaceholderPage title="Faturamento" />} />
                  <Route path="/hr/*" element={<PlaceholderPage title="RH" />} />
                  <Route path="/inventory/*" element={<PlaceholderPage title="Estoque" />} />
                  <Route path="/settings/entities" element={<EntitiesPage />} />
                  <Route path="/settings/*" element={<PlaceholderPage title="Ajustes" />} />
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

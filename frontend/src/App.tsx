import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom"
import { Toaster } from "@/components/ui/toaster"
import { ErrorBoundary } from "@/components/ErrorBoundary"
import { AppShell } from "@/components/layout/AppShell"
import { useAuth } from "@/providers/AuthProvider"
import { LoginPage } from "@/pages/LoginPage"
import { TransactionsPage } from "@/pages/TransactionsPage"
import { BankTransactionsPage } from "@/pages/BankTransactionsPage"
import { ReconciliationDashboardPage } from "@/pages/ReconciliationDashboardPage"
import { ReconciliationTasksPage } from "@/pages/ReconciliationTasksPage"
import { ReconciliationConfigsPage } from "@/pages/ReconciliationConfigsPage"
import { ReconciliationPipelinesPage } from "@/pages/ReconciliationPipelinesPage"
import { FinancialStatementsPage } from "@/pages/FinancialStatementsPage"
import { FinancialStatementTemplatesPage } from "@/pages/FinancialStatementTemplatesPage"
import { AccountsPage } from "@/pages/AccountsPage"
import { JournalEntriesPage } from "@/pages/JournalEntriesPage"
import { BillingPage } from "@/pages/BillingPage"
import { HRPage } from "@/pages/HRPage"
import { SettingsPage } from "@/pages/SettingsPage"

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth()
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />
}

function App() {
  console.log("📱 App component rendering...")
  
  return (
    <ErrorBoundary>
      <BrowserRouter
        future={{
          v7_startTransition: true,
          v7_relativeSplatPath: true,
        }}
      >
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/*"
            element={
              <PrivateRoute>
                <AppShell>
                  <Routes>
                    <Route path="/" element={<Navigate to="/accounting/transactions" replace />} />
                    <Route path="/accounting/transactions" element={<TransactionsPage />} />
                    <Route path="/accounting/journal-entries" element={<JournalEntriesPage />} />
                    <Route path="/accounting/accounts" element={<AccountsPage />} />
                    <Route path="/banking/bank-transactions" element={<BankTransactionsPage />} />
                    <Route path="/banking/reconciliation-dashboard" element={<ReconciliationDashboardPage />} />
                    <Route path="/banking/reconciliation-tasks" element={<ReconciliationTasksPage />} />
                    <Route path="/banking/reconciliation-configs" element={<ReconciliationConfigsPage />} />
                    <Route path="/banking/reconciliation-pipelines" element={<ReconciliationPipelinesPage />} />
                    <Route path="/financial-statements/statements" element={<FinancialStatementsPage />} />
                    <Route path="/financial-statements/templates" element={<FinancialStatementTemplatesPage />} />
                    <Route path="/billing" element={<BillingPage />} />
                    <Route path="/hr" element={<HRPage />} />
                    <Route path="/settings" element={<SettingsPage />} />
                  </Routes>
                </AppShell>
              </PrivateRoute>
            }
          />
        </Routes>
        <Toaster />
      </BrowserRouter>
    </ErrorBoundary>
  )
}

export default App


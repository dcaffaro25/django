import { useQuery } from "@tanstack/react-query"
import { PageHeader } from "@/components/layout/PageHeader"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { apiClient } from "@/lib/api-client"
import { useReconciliationDashboard } from "@/features/reconciliation"
import type { ReconciliationDashboard } from "@/types"
import { formatCurrency } from "@/lib/utils"
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts"

export function ReconciliationDashboardPage() {
  const { data, isLoading } = useReconciliationDashboard()

  if (isLoading) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Reconciliation Dashboard"
          description="Overview of unreconciled bank transactions and journal entries"
          breadcrumbs={[
            { label: "Home", href: "/" },
            { label: "Banking", href: "/banking" },
            { label: "Reconciliation Dashboard" },
          ]}
        />
        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader>
              <Skeleton className="h-6 w-48" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-8 w-24 mb-2" />
              <Skeleton className="h-4 w-32" />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <Skeleton className="h-6 w-48" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-8 w-24 mb-2" />
              <Skeleton className="h-4 w-32" />
            </CardContent>
          </Card>
        </div>
      </div>
    )
  }

  const chartData = data?.bank_transactions.daily.map((item, index) => ({
    date: new Date(item.date).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
    bankTransactions: item.count,
    bankTotal: item.total,
    journalEntries: data.journal_entries.daily[index]?.count || 0,
    journalTotal: data.journal_entries.daily[index]?.total || 0,
  })) || []

  return (
    <div className="space-y-6">
      <PageHeader
        title="Reconciliation Dashboard"
        description="Overview of unreconciled bank transactions and journal entries"
        breadcrumbs={[
          { label: "Home", href: "/" },
          { label: "Banking", href: "/banking" },
          { label: "Reconciliation Dashboard" },
        ]}
        actions={
          <Button onClick={() => window.location.href = "/banking/reconciliation-tasks"}>
            Start Reconciliation
          </Button>
        }
      />
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Unreconciled Bank Transactions</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{data?.bank_transactions.overall.count ?? 0}</div>
            <p className="text-muted-foreground">
              Total: {formatCurrency(data?.bank_transactions.overall.total ?? 0)}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Unreconciled Journal Entries</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{data?.journal_entries.overall.count ?? 0}</div>
            <p className="text-muted-foreground">
              Total: {formatCurrency(data?.journal_entries.overall.total ?? 0)}
            </p>
          </CardContent>
        </Card>
      </div>
      {chartData.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Daily Trends</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="bankTransactions" stroke="#8884d8" name="Bank Transactions" />
                <Line type="monotone" dataKey="journalEntries" stroke="#82ca9d" name="Journal Entries" />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}
    </div>
  )
}


import { useState } from "react"
import { ColumnDef } from "@tanstack/react-table"
import { Plus, Upload } from "lucide-react"
import { PageHeader } from "@/components/layout/PageHeader"
import { DataTable } from "@/components/ui/data-table"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { formatCurrency, formatDate } from "@/lib/utils"
import type { BankTransaction } from "@/types"
import { useQuery } from "@tanstack/react-query"
import { apiClient } from "@/lib/api-client"
import type { PaginatedResponse } from "@/types"
import { useTenant } from "@/providers/TenantProvider"

const columns: ColumnDef<BankTransaction>[] = [
  {
    accessorKey: "date",
    header: "Date",
    cell: ({ row }) => formatDate(row.original.date),
  },
  {
    accessorKey: "description",
    header: "Description",
  },
  {
    accessorKey: "amount",
    header: "Amount",
    cell: ({ row }) => formatCurrency(row.original.amount, "USD"),
  },
  {
    accessorKey: "reconciliation_status",
    header: "Status",
    cell: ({ row }) => {
      const status = row.original.reconciliation_status ?? "pending"
      const variant =
        status === "matched" ? "success" : status === "mixed" ? "warning" : "secondary"
      return <Badge variant={variant}>{status}</Badge>
    },
  },
]

export function BankTransactionsPage() {
  const { tenant } = useTenant()
  const [activeTab, setActiveTab] = useState("all")
  const [page, setPage] = useState(1)

  const { data: allData, isLoading: allLoading } = useQuery({
    queryKey: ["bank-transactions", tenant?.subdomain, "all", page],
    queryFn: () =>
      apiClient.get<PaginatedResponse<BankTransaction>>("/api/bank_transactions/", {
        page,
        page_size: 20,
      }),
    enabled: !!tenant, // Only fetch when tenant is set
  })

  const { data: unreconciledData, isLoading: unreconciledLoading } = useQuery({
    queryKey: ["bank-transactions", tenant?.subdomain, "unreconciled", page],
    queryFn: () =>
      apiClient.get<PaginatedResponse<BankTransaction>>("/api/bank_transactions/", {
        page,
        page_size: 20,
        unreconciled: true,
      }),
    enabled: !!tenant && activeTab === "unreconciled", // Only fetch when tenant is set and tab is active
  })

  const data = activeTab === "unreconciled" ? unreconciledData : allData
  const isLoading = activeTab === "unreconciled" ? unreconciledLoading : allLoading

  return (
    <div className="space-y-6">
      <PageHeader
        title="Bank Transactions"
        description="View and manage bank transactions imported from bank statements"
        breadcrumbs={[
          { label: "Home", href: "/" },
          { label: "Banking", href: "/banking" },
          { label: "Bank Transactions" },
        ]}
        actions={
          <>
            <Button variant="outline">
              <Upload className="mr-2 h-4 w-4" />
              Import OFX
            </Button>
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              Get Suggestions
            </Button>
          </>
        }
      />
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="all">All</TabsTrigger>
          <TabsTrigger value="unreconciled">Unreconciled</TabsTrigger>
          <TabsTrigger value="reconciled">Reconciled</TabsTrigger>
        </TabsList>
        <TabsContent value={activeTab} className="mt-4">
          <DataTable
            columns={columns}
            data={data?.results ?? []}
            loading={isLoading}
          />
        </TabsContent>
      </Tabs>
    </div>
  )
}


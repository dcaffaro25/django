import { useState, useEffect } from "react"
import { useQuery } from "@tanstack/react-query"
import { ColumnDef } from "@tanstack/react-table"
import { Plus, MoreHorizontal } from "lucide-react"
import { PageHeader } from "@/components/layout/PageHeader"
import { DataTable } from "@/components/ui/data-table"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { FilterBar, type FilterConfig } from "@/components/ui/filter-bar"
import { TransactionDetailDrawer, TransactionFormModal } from "@/features/transactions"
import { apiClient } from "@/lib/api-client"
import { formatCurrency, formatDate } from "@/lib/utils"
import type { Transaction, PaginatedResponse, Entity, Currency } from "@/types"
import { useTransactions, usePostTransaction, useUnpostTransaction } from "@/features/transactions"
import { useToast } from "@/components/ui/use-toast"
import { useTenant } from "@/providers/TenantProvider"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

const columns: (onPost: (id: number) => void, onUnpost: (id: number) => void) => ColumnDef<Transaction>[] = (onPost, onUnpost) => [
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
    accessorKey: "state",
    header: "Status",
    cell: ({ row }) => {
      const state = row.original.state
      const variant =
        state === "posted" ? "success" : state === "cancelled" ? "destructive" : "secondary"
      return <Badge variant={variant}>{state}</Badge>
    },
  },
  {
    accessorKey: "balance",
    header: "Balance",
    cell: ({ row }) => {
      const balance = row.original.balance ?? 0
      return balance === 0 ? (
        <Badge variant="success">Balanced</Badge>
      ) : (
        <Badge variant="warning">Unbalanced</Badge>
      )
    },
  },
  {
    id: "actions",
    cell: ({ row }) => {
      const transaction = row.original
      return (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon">
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {transaction.state === "pending" && (
              <DropdownMenuItem onClick={() => onPost(transaction.id)}>
                Post
              </DropdownMenuItem>
            )}
            {transaction.state === "posted" && (
              <DropdownMenuItem onClick={() => onUnpost(transaction.id)}>
                Unpost
              </DropdownMenuItem>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      )
    },
  },
]

export function TransactionsPage() {
  const { toast } = useToast()
  const { tenant } = useTenant()
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState<Record<string, unknown>>({})
  const [selectedTransaction, setSelectedTransaction] = useState<Transaction | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingTransaction, setEditingTransaction] = useState<Transaction | null>(null)

  const { data, isLoading, isError, error } = useTransactions({ page, page_size: 20, ...filters })
  
  // Debug logging
  useEffect(() => {
    if (tenant) {
      console.log("TransactionsPage - Tenant selected:", tenant.subdomain)
      console.log("TransactionsPage - Query state:", { isLoading, isError, hasData: !!data, error })
      console.log("TransactionsPage - API Client tenant ID:", apiClient.getTenantId())
    }
  }, [tenant, isLoading, isError, data, error])
  
  // Show message if no tenant is selected
  if (!tenant) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Transactions"
          description="View and manage all accounting transactions"
          breadcrumbs={[
            { label: "Home", href: "/" },
            { label: "Accounting", href: "/accounting" },
            { label: "Transactions" },
          ]}
        />
        <div className="flex h-64 items-center justify-center rounded-lg border bg-muted/50">
          <div className="text-center">
            <p className="text-lg font-medium text-muted-foreground">No tenant selected</p>
            <p className="mt-2 text-sm text-muted-foreground">
              Please select a tenant from the sidebar to view transactions
            </p>
          </div>
        </div>
      </div>
    )
  }
  
  // Show error message if query failed
  if (isError) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Transactions"
          description="View and manage all accounting transactions"
          breadcrumbs={[
            { label: "Home", href: "/" },
            { label: "Accounting", href: "/accounting" },
            { label: "Transactions" },
          ]}
        />
        <div className="flex h-64 items-center justify-center rounded-lg border border-destructive bg-destructive/10">
          <div className="text-center">
            <p className="text-lg font-medium text-destructive">Failed to load transactions</p>
            <p className="mt-2 text-sm text-muted-foreground">
              {error instanceof Error ? error.message : "An error occurred while loading transactions"}
            </p>
            <Button
              className="mt-4"
              onClick={() => window.location.reload()}
            >
              Retry
            </Button>
          </div>
        </div>
      </div>
    )
  }
  const postMutation = usePostTransaction()
  const unpostMutation = useUnpostTransaction()

  // Only fetch entities and currencies when tenant is available
  const { data: entitiesData } = useQuery({
    queryKey: ["entities", tenant?.subdomain],
    queryFn: () => apiClient.get<PaginatedResponse<Entity>>("/api/entities/"),
    enabled: !!tenant, // Only fetch when tenant is set
  })

  const { data: currenciesData } = useQuery({
    queryKey: ["currencies", tenant?.subdomain],
    queryFn: () => apiClient.get<PaginatedResponse<Currency>>("/api/currencies/"),
    enabled: !!tenant, // Only fetch when tenant is set
  })

  const filterConfig: FilterConfig[] = [
    {
      id: "date_from",
      type: "daterange",
      label: "Date Range",
    },
    {
      id: "state",
      type: "select",
      label: "Status",
      options: [
        { value: "pending", label: "Pending" },
        { value: "posted", label: "Posted" },
        { value: "cancelled", label: "Cancelled" },
      ],
    },
    {
      id: "description",
      type: "text",
      label: "Description",
      placeholder: "Search description...",
    },
  ]

  const handleRowClick = (transaction: Transaction) => {
    setSelectedTransaction(transaction)
    setDrawerOpen(true)
  }

  const handlePost = async (id: number) => {
    await postMutation.mutateAsync(id)
  }

  const handleUnpost = async (id: number) => {
    await unpostMutation.mutateAsync(id)
  }

  const handleCreate = () => {
    setEditingTransaction(null)
    setModalOpen(true)
  }

  const handleClearFilters = () => {
    setFilters({})
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Transactions"
        description="View and manage all accounting transactions"
        breadcrumbs={[
          { label: "Home", href: "/" },
          { label: "Accounting", href: "/accounting" },
          { label: "Transactions" },
        ]}
        actions={
          <Button onClick={handleCreate} size="lg" className="shadow-sm">
            <Plus className="mr-2 h-4 w-4" />
            Create Transaction
          </Button>
        }
      />
      <div className="rounded-xl border bg-card shadow-sm">
        <div className="p-6">
          <FilterBar
            filters={filters}
            onFilterChange={setFilters}
            filterConfig={filterConfig}
            onClear={handleClearFilters}
          />
        </div>
        <div className="border-t">
          <DataTable
            columns={columns(handlePost, handleUnpost)}
            data={data?.results ?? []}
            loading={isLoading}
            onRowClick={handleRowClick}
          />
        </div>
      </div>
      <TransactionDetailDrawer
        transaction={selectedTransaction}
        open={drawerOpen}
        onClose={() => {
          setDrawerOpen(false)
          setSelectedTransaction(null)
        }}
      />
      <TransactionFormModal
        open={modalOpen}
        onClose={() => {
          setModalOpen(false)
          setEditingTransaction(null)
        }}
        transaction={editingTransaction}
        entities={entitiesData?.results ?? []}
        currencies={currenciesData?.results ?? []}
      />
    </div>
  )
}


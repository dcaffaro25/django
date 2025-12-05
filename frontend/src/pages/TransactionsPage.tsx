import { useState } from "react"
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
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState<Record<string, unknown>>({})
  const [selectedTransaction, setSelectedTransaction] = useState<Transaction | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingTransaction, setEditingTransaction] = useState<Transaction | null>(null)

  const { data, isLoading } = useTransactions({ page, page_size: 20, ...filters })
  const postMutation = usePostTransaction()
  const unpostMutation = useUnpostTransaction()

  const { data: entitiesData } = useQuery({
    queryKey: ["entities"],
    queryFn: () => apiClient.get<PaginatedResponse<Entity>>("/api/entities/"),
  })

  const { data: currenciesData } = useQuery({
    queryKey: ["currencies"],
    queryFn: () => apiClient.get<PaginatedResponse<Currency>>("/api/currencies/"),
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
          <Button onClick={handleCreate}>
            <Plus className="mr-2 h-4 w-4" />
            Create Transaction
          </Button>
        }
      />
      <FilterBar
        filters={filters}
        onFilterChange={setFilters}
        filterConfig={filterConfig}
        onClear={handleClearFilters}
      />
      <DataTable
        columns={columns(handlePost, handleUnpost)}
        data={data?.results ?? []}
        loading={isLoading}
        onRowClick={handleRowClick}
      />
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


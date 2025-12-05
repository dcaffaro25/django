import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { ColumnDef } from "@tanstack/react-table"
import { Plus, ChevronRight, ChevronDown } from "lucide-react"
import { PageHeader } from "@/components/layout/PageHeader"
import { DataTable } from "@/components/ui/data-table"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { formatCurrency } from "@/lib/utils"
import type { Account, PaginatedResponse } from "@/types"
import { useAccounts } from "@/features/accounts"
import { apiClient } from "@/lib/api-client"

const buildAccountTree = (accounts: Account[]): Account[] => {
  const accountMap = new Map<number, Account & { children: Account[] }>()
  const rootAccounts: Account[] = []

  accounts.forEach((account) => {
    accountMap.set(account.id, { ...account, children: [] })
  })

  accounts.forEach((account) => {
    const accountWithChildren = accountMap.get(account.id)!
    if (account.parent) {
      const parent = accountMap.get(account.parent)
      if (parent) {
        parent.children.push(accountWithChildren)
      } else {
        rootAccounts.push(accountWithChildren)
      }
    } else {
      rootAccounts.push(accountWithChildren)
    }
  })

  return rootAccounts
}

const flattenTree = (
  accounts: (Account & { children?: Account[] })[],
  expanded: Set<number>,
  level = 0
): Account[] => {
  const result: Account[] = []
  accounts.forEach((account) => {
    result.push({ ...account, level })
    if (account.children && expanded.has(account.id)) {
      result.push(...flattenTree(account.children, expanded, level + 1))
    }
  })
  return result
}

const columns: ColumnDef<Account & { level?: number }>[] = [
  {
    accessorKey: "account_code",
    header: "Code",
    cell: ({ row }) => {
      const level = row.original.level || 0
      return (
        <div className="flex items-center gap-2" style={{ paddingLeft: `${level * 20}px` }}>
          {row.original.level !== undefined && (
            <span className="text-muted-foreground">└</span>
          )}
          {row.original.account_code || "-"}
        </div>
      )
    },
  },
  {
    accessorKey: "name",
    header: "Name",
    cell: ({ row }) => {
      const level = row.original.level || 0
      return <div style={{ paddingLeft: `${level * 20}px` }}>{row.original.name}</div>
    },
  },
  {
    accessorKey: "current_balance",
    header: "Balance",
    cell: ({ row }) => formatCurrency(row.original.current_balance || 0),
  },
  {
    accessorKey: "is_active",
    header: "Status",
    cell: ({ row }) => (
      <Badge variant={row.original.is_active ? "success" : "secondary"}>
        {row.original.is_active ? "Active" : "Inactive"}
      </Badge>
    ),
  },
]

export function AccountsPage() {
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const [viewMode, setViewMode] = useState<"tree" | "list">("tree")

  const { data, isLoading } = useAccounts()

  const toggleExpand = (id: number) => {
    const newExpanded = new Set(expanded)
    if (newExpanded.has(id)) {
      newExpanded.delete(id)
    } else {
      newExpanded.add(id)
    }
    setExpanded(newExpanded)
  }

  const displayData =
    viewMode === "tree" && data?.results
      ? flattenTree(buildAccountTree(data.results), expanded)
      : data?.results || []

  return (
    <div className="space-y-6">
      <PageHeader
        title="Chart of Accounts"
        description="Manage hierarchical chart of accounts"
        breadcrumbs={[
          { label: "Home", href: "/" },
          { label: "Accounting", href: "/accounting" },
          { label: "Chart of Accounts" },
        ]}
        actions={
          <>
            <Button
              variant={viewMode === "tree" ? "default" : "outline"}
              onClick={() => setViewMode("tree")}
            >
              Tree View
            </Button>
            <Button
              variant={viewMode === "list" ? "default" : "outline"}
              onClick={() => setViewMode("list")}
            >
              List View
            </Button>
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              Create Account
            </Button>
          </>
        }
      />
      <DataTable columns={columns} data={displayData} loading={isLoading} />
    </div>
  )
}

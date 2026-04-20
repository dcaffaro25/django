import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { ColumnDef } from "@tanstack/react-table"
import { Plus, FileDown } from "lucide-react"
import { PageHeader } from "@/components/layout/PageHeader"
import { DataTable } from "@/components/ui/data-table"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { formatDate } from "@/lib/utils"
import type { FinancialStatement, PaginatedResponse } from "@/types"
import { apiClient } from "@/lib/api-client"
import { useTenant } from "@/providers/TenantProvider"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

const columns: ColumnDef<FinancialStatement>[] = [
  {
    accessorKey: "name",
    header: "Name",
  },
  {
    accessorKey: "report_type",
    header: "Type",
    cell: ({ row }) => {
      const type = row.original.report_type
      return <Badge variant="secondary">{type.replace("_", " ")}</Badge>
    },
  },
  {
    accessorKey: "template_name",
    header: "Template",
  },
  {
    accessorKey: "start_date",
    header: "Start Date",
    cell: ({ row }) => formatDate(row.original.start_date),
  },
  {
    accessorKey: "end_date",
    header: "End Date",
    cell: ({ row }) => formatDate(row.original.end_date),
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => {
      const status = row.original.status
      const variant =
        status === "final" ? "success" : status === "archived" ? "secondary" : "warning"
      return <Badge variant={variant}>{status}</Badge>
    },
  },
]

export function FinancialStatementsPage() {
  const { tenant } = useTenant()
  const { data, isLoading } = useQuery({
    queryKey: ["financial-statements", tenant?.subdomain],
    queryFn: () =>
      apiClient.get<PaginatedResponse<FinancialStatement>>(
        "/api/financial-statements/"
      ),
    enabled: !!tenant, // Only fetch when tenant is set
  })

  const handleExport = async (id: number, format: "excel" | "markdown" | "html") => {
    try {
      const response = await apiClient.get(
        `/api/financial-statements/${id}/export_${format}/`,
        {},
        { responseType: "blob" }
      )
      const url = window.URL.createObjectURL(new Blob([response]))
      const link = document.createElement("a")
      link.href = url
      link.setAttribute("download", `statement-${id}.${format === "excel" ? "xlsx" : format}`)
      document.body.appendChild(link)
      link.click()
      link.remove()
    } catch (error) {
      console.error("Export failed:", error)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Financial Statements"
        description="Generate, view, and manage financial statements"
        breadcrumbs={[
          { label: "Home", href: "/" },
          { label: "Financial Statements", href: "/financial-statements" },
          { label: "Statements" },
        ]}
        actions={
          <Button>
            <Plus className="mr-2 h-4 w-4" />
            Generate Statement
          </Button>
        }
      />
      <DataTable
        columns={[
          ...columns,
          {
            id: "actions",
            header: "Actions",
            cell: ({ row }) => (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="sm">
                    <FileDown className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent>
                  <DropdownMenuItem onClick={() => handleExport(row.original.id, "excel")}>
                    Export Excel
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => handleExport(row.original.id, "markdown")}>
                    Export Markdown
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => handleExport(row.original.id, "html")}>
                    Export HTML
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ),
          },
        ]}
        data={data?.results ?? []}
        loading={isLoading}
      />
    </div>
  )
}

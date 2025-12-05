import { useState } from "react"
import { ColumnDef } from "@tanstack/react-table"
import { Plus, MoreHorizontal } from "lucide-react"
import { PageHeader } from "@/components/layout/PageHeader"
import { DataTable } from "@/components/ui/data-table"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import {
  useEmployees,
  useCreateEmployee,
  useUpdateEmployee,
  useDeleteEmployee,
  usePositions,
  useCreatePosition,
  useUpdatePosition,
  useDeletePosition,
  useTimeTracking,
  useApproveTimeTracking,
  useRejectTimeTracking,
  usePayrolls,
  useGenerateMonthlyPayroll,
  useRecurringAdjustments,
} from "@/features/hr"
import type { Employee, Position, TimeTracking, Payroll } from "@/features/hr"
import { formatDate } from "@/lib/utils"

// Employee columns
const employeeColumns: ColumnDef<Employee>[] = [
  {
    accessorKey: "first_name",
    header: "First Name",
  },
  {
    accessorKey: "last_name",
    header: "Last Name",
  },
  {
    accessorKey: "email",
    header: "Email",
  },
  {
    accessorKey: "position_name",
    header: "Position",
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => {
      const status = row.original.status
      const variant = status === "active" ? "success" : "secondary"
      return <Badge variant={variant}>{status}</Badge>
    },
  },
]

// Position columns
const positionColumns: ColumnDef<Position>[] = [
  {
    accessorKey: "name",
    header: "Name",
  },
  {
    accessorKey: "department",
    header: "Department",
  },
  {
    accessorKey: "is_active",
    header: "Active",
    cell: ({ row }) => {
      return row.original.is_active ? (
        <Badge variant="success">Yes</Badge>
      ) : (
        <Badge variant="secondary">No</Badge>
      )
    },
  },
]

// Time Tracking columns
const timeTrackingColumns: ColumnDef<TimeTracking>[] = [
  {
    accessorKey: "employee_name",
    header: "Employee",
  },
  {
    accessorKey: "date",
    header: "Date",
    cell: ({ row }) => formatDate(row.original.date),
  },
  {
    accessorKey: "hours",
    header: "Hours",
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => {
      const status = row.original.status
      const variant =
        status === "approved" ? "success" : status === "rejected" ? "destructive" : "secondary"
      return <Badge variant={variant}>{status}</Badge>
    },
  },
]

// Payroll columns
const payrollColumns: ColumnDef<Payroll>[] = [
  {
    accessorKey: "employee_name",
    header: "Employee",
  },
  {
    accessorKey: "period_start",
    header: "Period Start",
    cell: ({ row }) => formatDate(row.original.period_start),
  },
  {
    accessorKey: "period_end",
    header: "Period End",
    cell: ({ row }) => formatDate(row.original.period_end),
  },
  {
    accessorKey: "net_salary",
    header: "Net Salary",
    cell: ({ row }) => `$${row.original.net_salary.toFixed(2)}`,
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => {
      const status = row.original.status
      const variant =
        status === "paid" ? "success" : status === "final" ? "default" : "secondary"
      return <Badge variant={variant}>{status}</Badge>
    },
  },
]

export function HRPage() {
  const [activeTab, setActiveTab] = useState("employees")
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [itemToDelete, setItemToDelete] = useState<{ type: string; id: number } | null>(null)

  // Employees
  const { data: employees, isLoading: employeesLoading } = useEmployees()
  const deleteEmployee = useDeleteEmployee()

  // Positions
  const { data: positions, isLoading: positionsLoading } = usePositions()
  const deletePosition = useDeletePosition()

  // Time Tracking
  const { data: timeTracking, isLoading: timeTrackingLoading } = useTimeTracking()
  const approveTime = useApproveTimeTracking()
  const rejectTime = useRejectTimeTracking()

  // Payrolls
  const { data: payrolls, isLoading: payrollsLoading } = usePayrolls()
  const generatePayroll = useGenerateMonthlyPayroll()

  const handleDelete = () => {
    if (!itemToDelete) return

    if (itemToDelete.type === "employee") {
      deleteEmployee.mutate(itemToDelete.id, {
        onSuccess: () => {
          setDeleteDialogOpen(false)
          setItemToDelete(null)
        },
      })
    } else if (itemToDelete.type === "position") {
      deletePosition.mutate(itemToDelete.id, {
        onSuccess: () => {
          setDeleteDialogOpen(false)
          setItemToDelete(null)
        },
      })
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Human Resources"
        description="Manage employees, positions, time tracking, and payroll"
        breadcrumbs={[
          { label: "Home", href: "/" },
          { label: "HR" },
        ]}
      />

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="employees">Employees</TabsTrigger>
          <TabsTrigger value="positions">Positions</TabsTrigger>
          <TabsTrigger value="time-tracking">Time Tracking</TabsTrigger>
          <TabsTrigger value="payroll">Payroll</TabsTrigger>
        </TabsList>

        <TabsContent value="employees" className="space-y-4">
          <div className="flex justify-end">
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              New Employee
            </Button>
          </div>
          <DataTable
            data={employees?.results || []}
            columns={employeeColumns}
            isLoading={employeesLoading}
            rowActions={(row) => (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon">
                    <MoreHorizontal className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={() => {}}>Edit</DropdownMenuItem>
                  <DropdownMenuItem
                    onClick={() => {
                      setItemToDelete({ type: "employee", id: row.id })
                      setDeleteDialogOpen(true)
                    }}
                    className="text-destructive"
                  >
                    Delete
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          />
        </TabsContent>

        <TabsContent value="positions" className="space-y-4">
          <div className="flex justify-end">
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              New Position
            </Button>
          </div>
          <DataTable
            data={positions?.results || []}
            columns={positionColumns}
            isLoading={positionsLoading}
            rowActions={(row) => (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon">
                    <MoreHorizontal className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={() => {}}>Edit</DropdownMenuItem>
                  <DropdownMenuItem
                    onClick={() => {
                      setItemToDelete({ type: "position", id: row.id })
                      setDeleteDialogOpen(true)
                    }}
                    className="text-destructive"
                  >
                    Delete
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          />
        </TabsContent>

        <TabsContent value="time-tracking" className="space-y-4">
          <div className="flex justify-end">
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              New Time Entry
            </Button>
          </div>
          <DataTable
            data={timeTracking?.results || []}
            columns={timeTrackingColumns}
            isLoading={timeTrackingLoading}
            rowActions={(row) => {
              const entry = row.original
              return (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon">
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    {entry.status === "pending" && (
                      <>
                        <DropdownMenuItem onClick={() => approveTime.mutate(entry.id)}>
                          Approve
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => rejectTime.mutate(entry.id)}>
                          Reject
                        </DropdownMenuItem>
                      </>
                    )}
                    <DropdownMenuItem onClick={() => {}}>Edit</DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              )
            }}
          />
        </TabsContent>

        <TabsContent value="payroll" className="space-y-4">
          <div className="flex justify-end gap-2">
            <Button
              onClick={() => {
                const now = new Date()
                const firstDay = new Date(now.getFullYear(), now.getMonth(), 1)
                const lastDay = new Date(now.getFullYear(), now.getMonth() + 1, 0)
                generatePayroll.mutate({
                  period_start: firstDay.toISOString().split("T")[0],
                  period_end: lastDay.toISOString().split("T")[0],
                })
              }}
            >
              Generate Monthly Payroll
            </Button>
          </div>
          <DataTable
            data={payrolls?.results || []}
            columns={payrollColumns}
            isLoading={payrollsLoading}
            rowActions={(row) => (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon">
                    <MoreHorizontal className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={() => {}}>View Details</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          />
        </TabsContent>
      </Tabs>

      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Are you sure?</AlertDialogTitle>
            <AlertDialogDescription>
              This action cannot be undone. This will permanently delete this item.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}


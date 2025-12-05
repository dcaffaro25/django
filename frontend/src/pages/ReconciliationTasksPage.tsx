import { useState } from "react"
import { ColumnDef } from "@tanstack/react-table"
import { Play, RefreshCw } from "lucide-react"
import { PageHeader } from "@/components/layout/PageHeader"
import { DataTable } from "@/components/ui/data-table"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Checkbox } from "@/components/ui/checkbox"
import { formatDateTime } from "@/lib/utils"
import type { ReconciliationTask } from "@/types"
import { useReconciliationTasks, useStartReconciliation, useReconciliationConfigs } from "@/features/reconciliation"
import { Progress } from "@/components/ui/progress"

const columns: ColumnDef<ReconciliationTask>[] = [
  {
    accessorKey: "created_at",
    header: "Created",
    cell: ({ row }) => formatDateTime(row.original.created_at),
  },
  {
    accessorKey: "config_name",
    header: "Config/Pipeline",
    cell: ({ row }) => row.original.config_name || row.original.pipeline_name || "-",
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => {
      const status = row.original.status
      const variant =
        status === "completed"
          ? "success"
          : status === "failed"
          ? "destructive"
          : status === "running"
          ? "warning"
          : "secondary"
      return <Badge variant={variant}>{status}</Badge>
    },
  },
  {
    accessorKey: "suggestion_count",
    header: "Suggestions",
    cell: ({ row }) => row.original.suggestion_count || 0,
  },
  {
    accessorKey: "matched_bank_transactions",
    header: "Matched",
    cell: ({ row }) => row.original.matched_bank_transactions || 0,
  },
  {
    accessorKey: "duration_seconds",
    header: "Duration",
    cell: ({ row }) => {
      const duration = row.original.duration_seconds
      return duration ? `${duration}s` : "-"
    },
  },
]

export function ReconciliationTasksPage() {
  const [activeTab, setActiveTab] = useState("all")
  const [startDialogOpen, setStartDialogOpen] = useState(false)
  const [selectedConfig, setSelectedConfig] = useState<string>("")
  const [autoMatch, setAutoMatch] = useState(false)

  const { data, isLoading } = useReconciliationTasks({
    status: activeTab === "all" ? undefined : activeTab,
  })
  const { data: configsData } = useReconciliationConfigs()
  const startMutation = useStartReconciliation()

  const handleStart = async () => {
    await startMutation.mutateAsync({
      config_id: selectedConfig ? Number(selectedConfig) : undefined,
      auto_match_100: autoMatch,
    })
    setStartDialogOpen(false)
    setSelectedConfig("")
    setAutoMatch(false)
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Reconciliation Tasks"
        description="View and manage reconciliation task executions"
        breadcrumbs={[
          { label: "Home", href: "/" },
          { label: "Banking", href: "/banking" },
          { label: "Reconciliation Tasks" },
        ]}
        actions={
          <Button onClick={() => setStartDialogOpen(true)}>
            <Play className="mr-2 h-4 w-4" />
            Start Reconciliation
          </Button>
        }
      />
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="all">All</TabsTrigger>
          <TabsTrigger value="queued">Queued</TabsTrigger>
          <TabsTrigger value="running">Running</TabsTrigger>
          <TabsTrigger value="completed">Completed</TabsTrigger>
          <TabsTrigger value="failed">Failed</TabsTrigger>
        </TabsList>
        <TabsContent value={activeTab} className="mt-4">
          <DataTable columns={columns} data={data?.results ?? []} loading={isLoading} />
        </TabsContent>
      </Tabs>

      <Dialog open={startDialogOpen} onOpenChange={setStartDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Start Reconciliation</DialogTitle>
            <DialogDescription>
              Select a reconciliation config and options to start a new task.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Reconciliation Config</Label>
              <Select value={selectedConfig} onValueChange={setSelectedConfig}>
                <SelectTrigger>
                  <SelectValue placeholder="Select config" />
                </SelectTrigger>
                <SelectContent>
                  {configsData?.results.map((config) => (
                    <SelectItem key={config.id} value={config.id.toString()}>
                      {config.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center space-x-2">
              <Checkbox
                id="auto-match"
                checked={autoMatch}
                onCheckedChange={(checked) => setAutoMatch(checked === true)}
              />
              <Label htmlFor="auto-match" className="cursor-pointer">
                Auto-apply perfect matches (100%)
              </Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setStartDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleStart} disabled={startMutation.isPending}>
              {startMutation.isPending ? "Starting..." : "Start"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

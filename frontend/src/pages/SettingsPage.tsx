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
  useIntegrationRules,
  useCreateIntegrationRule,
  useUpdateIntegrationRule,
  useDeleteIntegrationRule,
  useSubstitutionRules,
  useCreateSubstitutionRule,
  useUpdateSubstitutionRule,
  useDeleteSubstitutionRule,
} from "@/features/settings"
import type { IntegrationRule, SubstitutionRule } from "@/features/settings"

// Integration Rule columns
const integrationRuleColumns: ColumnDef<IntegrationRule>[] = [
  {
    accessorKey: "name",
    header: "Name",
  },
  {
    accessorKey: "trigger_event",
    header: "Trigger Event",
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
  {
    accessorKey: "priority",
    header: "Priority",
  },
]

// Substitution Rule columns
const substitutionRuleColumns: ColumnDef<SubstitutionRule>[] = [
  {
    accessorKey: "name",
    header: "Name",
  },
  {
    accessorKey: "pattern",
    header: "Pattern",
  },
  {
    accessorKey: "replacement",
    header: "Replacement",
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
  {
    accessorKey: "priority",
    header: "Priority",
  },
]

export function SettingsPage() {
  const [activeTab, setActiveTab] = useState("integration-rules")
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [itemToDelete, setItemToDelete] = useState<{ type: string; id: number } | null>(null)

  // Integration Rules
  const { data: integrationRules, isLoading: integrationRulesLoading } = useIntegrationRules()
  const deleteIntegrationRule = useDeleteIntegrationRule()

  // Substitution Rules
  const { data: substitutionRules, isLoading: substitutionRulesLoading } = useSubstitutionRules()
  const deleteSubstitutionRule = useDeleteSubstitutionRule()

  const handleDelete = () => {
    if (!itemToDelete) return

    if (itemToDelete.type === "integration") {
      deleteIntegrationRule.mutate(itemToDelete.id, {
        onSuccess: () => {
          setDeleteDialogOpen(false)
          setItemToDelete(null)
        },
      })
    } else if (itemToDelete.type === "substitution") {
      deleteSubstitutionRule.mutate(itemToDelete.id, {
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
        title="Settings"
        description="Manage integration rules and substitution rules"
        breadcrumbs={[
          { label: "Home", href: "/" },
          { label: "Settings" },
        ]}
      />

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="integration-rules">Integration Rules</TabsTrigger>
          <TabsTrigger value="substitution-rules">Substitution Rules</TabsTrigger>
        </TabsList>

        <TabsContent value="integration-rules" className="space-y-4">
          <div className="flex justify-end">
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              New Integration Rule
            </Button>
          </div>
          <DataTable
            data={integrationRules?.results || []}
            columns={integrationRuleColumns}
            isLoading={integrationRulesLoading}
            rowActions={(row) => (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon">
                    <MoreHorizontal className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={() => {}}>Edit</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => {}}>Test</DropdownMenuItem>
                  <DropdownMenuItem
                    onClick={() => {
                      setItemToDelete({ type: "integration", id: row.id })
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

        <TabsContent value="substitution-rules" className="space-y-4">
          <div className="flex justify-end">
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              New Substitution Rule
            </Button>
          </div>
          <DataTable
            data={substitutionRules?.results || []}
            columns={substitutionRuleColumns}
            isLoading={substitutionRulesLoading}
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
                      setItemToDelete({ type: "substitution", id: row.id })
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
      </Tabs>

      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Are you sure?</AlertDialogTitle>
            <AlertDialogDescription>
              This action cannot be undone. This will permanently delete this rule.
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


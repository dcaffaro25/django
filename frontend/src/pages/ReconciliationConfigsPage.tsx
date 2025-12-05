import { useState } from "react"
import { ColumnDef } from "@tanstack/react-table"
import { Plus } from "lucide-react"
import { PageHeader } from "@/components/layout/PageHeader"
import { DataTable } from "@/components/ui/data-table"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { formatDateTime } from "@/lib/utils"
import type { ReconciliationConfig } from "@/types"
import { useReconciliationConfigs, useCreateReconciliationConfig } from "@/features/reconciliation"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"
import { useForm } from "react-hook-form"

const columns: ColumnDef<ReconciliationConfig>[] = [
  {
    accessorKey: "name",
    header: "Name",
  },
  {
    accessorKey: "scope",
    header: "Scope",
    cell: ({ row }) => {
      const scope = row.original.scope
      return <Badge variant="secondary">{scope}</Badge>
    },
  },
  {
    accessorKey: "is_default",
    header: "Default",
    cell: ({ row }) => {
      return row.original.is_default ? (
        <Badge variant="success">Yes</Badge>
      ) : (
        <Badge variant="secondary">No</Badge>
      )
    },
  },
  {
    accessorKey: "min_confidence",
    header: "Min Confidence",
    cell: ({ row }) => (row.original.min_confidence || 0) * 100 + "%",
  },
  {
    accessorKey: "updated_at",
    header: "Updated",
    cell: ({ row }) => formatDateTime(row.original.updated_at),
  },
]

export function ReconciliationConfigsPage() {
  const [modalOpen, setModalOpen] = useState(false)
  const { data, isLoading } = useReconciliationConfigs()
  const createMutation = useCreateReconciliationConfig()

  const { register, handleSubmit, formState: { errors }, reset } = useForm<Partial<ReconciliationConfig>>({
    defaultValues: {
      scope: "company",
      weight_embedding: 0.4,
      weight_amount: 0.3,
      weight_currency: 0.1,
      weight_date: 0.2,
      min_confidence: 0.7,
      max_suggestions: 10,
    },
  })

  const onSubmit = async (data: Partial<ReconciliationConfig>) => {
    await createMutation.mutateAsync(data)
    setModalOpen(false)
    reset()
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Reconciliation Configurations"
        description="Create and manage reconciliation matching configurations"
        breadcrumbs={[
          { label: "Home", href: "/" },
          { label: "Banking", href: "/banking" },
          { label: "Reconciliation Configurations" },
        ]}
        actions={
          <Button onClick={() => setModalOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            Create Config
          </Button>
        }
      />
      <DataTable columns={columns} data={data?.results ?? []} loading={isLoading} />

      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Create Reconciliation Config</DialogTitle>
            <DialogDescription>
              Configure matching rules, weights, and tolerances for reconciliation.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <Accordion type="single" collapsible className="w-full">
              <AccordionItem value="basic">
                <AccordionTrigger>Basic Information</AccordionTrigger>
                <AccordionContent className="space-y-4">
                  <div className="space-y-2">
                    <Label>
                      Name <span className="text-destructive">*</span>
                    </Label>
                    <Input {...register("name", { required: true })} />
                    {errors.name && (
                      <p className="text-sm text-destructive">Name is required</p>
                    )}
                  </div>
                  <div className="space-y-2">
                    <Label>Description</Label>
                    <Textarea {...register("description")} />
                  </div>
                  <div className="space-y-2">
                    <Label>Scope</Label>
                    <select
                      {...register("scope")}
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    >
                      <option value="global">Global</option>
                      <option value="company">Company</option>
                      <option value="user">User</option>
                      <option value="company_user">Company + User</option>
                    </select>
                  </div>
                </AccordionContent>
              </AccordionItem>

              <AccordionItem value="weights">
                <AccordionTrigger>Scoring Weights</AccordionTrigger>
                <AccordionContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label>Embedding Weight</Label>
                      <Input
                        type="number"
                        step="0.1"
                        min="0"
                        max="1"
                        {...register("weight_embedding", { valueAsNumber: true })}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Amount Weight</Label>
                      <Input
                        type="number"
                        step="0.1"
                        min="0"
                        max="1"
                        {...register("weight_amount", { valueAsNumber: true })}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Currency Weight</Label>
                      <Input
                        type="number"
                        step="0.1"
                        min="0"
                        max="1"
                        {...register("weight_currency", { valueAsNumber: true })}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Date Weight</Label>
                      <Input
                        type="number"
                        step="0.1"
                        min="0"
                        max="1"
                        {...register("weight_date", { valueAsNumber: true })}
                      />
                    </div>
                  </div>
                </AccordionContent>
              </AccordionItem>

              <AccordionItem value="thresholds">
                <AccordionTrigger>Thresholds</AccordionTrigger>
                <AccordionContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label>Min Confidence</Label>
                      <Input
                        type="number"
                        step="0.1"
                        min="0"
                        max="1"
                        {...register("min_confidence", { valueAsNumber: true })}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Max Suggestions</Label>
                      <Input
                        type="number"
                        {...register("max_suggestions", { valueAsNumber: true })}
                      />
                    </div>
                  </div>
                </AccordionContent>
              </AccordionItem>
            </Accordion>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setModalOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? "Creating..." : "Create"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}

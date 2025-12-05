import * as React from "react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { DatePicker } from "@/components/ui/date-picker"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import type { Transaction } from "@/types"
import { useCreateTransaction, useUpdateTransaction } from "../hooks/use-transactions"

const transactionSchema = z.object({
  date: z.date(),
  description: z.string().min(1, "Description is required"),
  amount: z.number().positive("Amount must be positive"),
  entity: z.number(),
  currency: z.number(),
})

type TransactionFormData = z.infer<typeof transactionSchema>

interface TransactionFormModalProps {
  open: boolean
  onClose: () => void
  transaction?: Transaction | null
  entities?: Array<{ id: number; name: string }>
  currencies?: Array<{ id: number; code: string; name: string }>
}

export function TransactionFormModal({
  open,
  onClose,
  transaction,
  entities = [],
  currencies = [],
}: TransactionFormModalProps) {
  const isEdit = !!transaction
  const createMutation = useCreateTransaction()
  const updateMutation = useUpdateTransaction()

  const {
    register,
    handleSubmit,
    formState: { errors },
    setValue,
    watch,
    reset,
  } = useForm<TransactionFormData>({
    resolver: zodResolver(transactionSchema),
    defaultValues: transaction
      ? {
          date: new Date(transaction.date),
          description: transaction.description,
          amount: transaction.amount,
          entity: transaction.entity,
          currency: transaction.currency,
        }
      : undefined,
  })

  React.useEffect(() => {
    if (transaction) {
      reset({
        date: new Date(transaction.date),
        description: transaction.description,
        amount: transaction.amount,
        entity: transaction.entity,
        currency: transaction.currency,
      })
    } else {
      reset()
    }
  }, [transaction, reset])

  const onSubmit = async (data: TransactionFormData) => {
    try {
      if (isEdit && transaction) {
        await updateMutation.mutateAsync({
          id: transaction.id,
          data,
        })
      } else {
        await createMutation.mutateAsync(data)
      }
      onClose()
      reset()
    } catch (error) {
      console.error("Error saving transaction:", error)
    }
  }

  const dateValue = watch("date")

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit Transaction" : "Create Transaction"}</DialogTitle>
          <DialogDescription>
            {isEdit
              ? "Update the transaction details below."
              : "Fill in the details to create a new transaction."}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <DatePicker
              label="Date"
              value={dateValue}
              onChange={(date) => setValue("date", date || new Date())}
              required
              error={errors.date?.message}
            />
            <div className="space-y-2">
              <Label>
                Entity <span className="text-destructive">*</span>
              </Label>
              <Select
                value={watch("entity")?.toString()}
                onValueChange={(val) => setValue("entity", Number(val))}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select entity" />
                </SelectTrigger>
                <SelectContent>
                  {entities.map((entity) => (
                    <SelectItem key={entity.id} value={entity.id.toString()}>
                      {entity.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {errors.entity && (
                <p className="text-sm text-destructive">{errors.entity.message}</p>
              )}
            </div>
          </div>

          <div className="space-y-2">
            <Label>
              Description <span className="text-destructive">*</span>
            </Label>
            <Input
              {...register("description")}
              placeholder="Enter description"
            />
            {errors.description && (
              <p className="text-sm text-destructive">{errors.description.message}</p>
            )}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>
                Amount <span className="text-destructive">*</span>
              </Label>
              <Input
                type="number"
                step="0.01"
                {...register("amount", { valueAsNumber: true })}
                placeholder="0.00"
              />
              {errors.amount && (
                <p className="text-sm text-destructive">{errors.amount.message}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label>
                Currency <span className="text-destructive">*</span>
              </Label>
              <Select
                value={watch("currency")?.toString()}
                onValueChange={(val) => setValue("currency", Number(val))}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select currency" />
                </SelectTrigger>
                <SelectContent>
                  {currencies.map((currency) => (
                    <SelectItem key={currency.id} value={currency.id.toString()}>
                      {currency.code} - {currency.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {errors.currency && (
                <p className="text-sm text-destructive">{errors.currency.message}</p>
              )}
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={createMutation.isPending || updateMutation.isPending}
            >
              {createMutation.isPending || updateMutation.isPending
                ? "Saving..."
                : isEdit
                ? "Update"
                : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}


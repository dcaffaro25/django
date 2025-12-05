import { Drawer } from "@/components/ui/drawer"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Badge } from "@/components/ui/badge"
import { formatCurrency, formatDate } from "@/lib/utils"
import type { Transaction, JournalEntry } from "@/types"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"

interface TransactionDetailDrawerProps {
  transaction: Transaction | null
  open: boolean
  onClose: () => void
}

export function TransactionDetailDrawer({
  transaction,
  open,
  onClose,
}: TransactionDetailDrawerProps) {
  if (!transaction) return null

  const isBalanced = (transaction.balance ?? 0) === 0

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={`Transaction #${transaction.id}`}
      width="800px"
    >
      <Tabs defaultValue="overview" className="w-full">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="journal-entries">
            Journal Entries ({transaction.journal_entries?.length ?? 0})
          </TabsTrigger>
          <TabsTrigger value="reconciliations">Reconciliations</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-muted-foreground">Date</label>
              <p className="text-sm">{formatDate(transaction.date)}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Amount</label>
              <p className="text-sm">{formatCurrency(transaction.amount)}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Status</label>
              <div className="mt-1">
                <Badge
                  variant={
                    transaction.state === "posted"
                      ? "success"
                      : transaction.state === "cancelled"
                      ? "destructive"
                      : "secondary"
                  }
                >
                  {transaction.state}
                </Badge>
              </div>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Balance</label>
              <div className="mt-1">
                <Badge variant={isBalanced ? "success" : "warning"}>
                  {isBalanced ? "Balanced" : "Unbalanced"}
                </Badge>
              </div>
            </div>
            <div className="col-span-2">
              <label className="text-sm font-medium text-muted-foreground">Description</label>
              <p className="text-sm">{transaction.description}</p>
            </div>
          </div>
        </TabsContent>

        <TabsContent value="journal-entries">
          {transaction.journal_entries && transaction.journal_entries.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Account</TableHead>
                  <TableHead>Description</TableHead>
                  <TableHead className="text-right">Debit</TableHead>
                  <TableHead className="text-right">Credit</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {transaction.journal_entries.map((entry: JournalEntry) => (
                  <TableRow key={entry.id}>
                    <TableCell>{entry.account}</TableCell>
                    <TableCell>{entry.description}</TableCell>
                    <TableCell className="text-right">
                      {entry.debit_amount ? formatCurrency(entry.debit_amount) : "-"}
                    </TableCell>
                    <TableCell className="text-right">
                      {entry.credit_amount ? formatCurrency(entry.credit_amount) : "-"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="text-sm text-muted-foreground">No journal entries</p>
          )}
        </TabsContent>

        <TabsContent value="reconciliations">
          <p className="text-sm text-muted-foreground">Reconciliation information coming soon...</p>
        </TabsContent>
      </Tabs>
    </Drawer>
  )
}


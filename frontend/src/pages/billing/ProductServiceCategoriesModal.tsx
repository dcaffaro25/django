import { useState } from "react"
import { Plus, Trash2 } from "lucide-react"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import {
  useProductServiceCategories, useDeleteProductServiceCategory,
  useSaveProductServiceCategory,
} from "@/features/billing"
import { useUserRole } from "@/features/auth/useUserRole"

export function ProductServiceCategoriesModal({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  const cats = useProductServiceCategories()
  const save = useSaveProductServiceCategory()
  const del = useDeleteProductServiceCategory()
  const { canWrite } = useUserRole()

  const [newName, setNewName] = useState("")
  const [newParent, setNewParent] = useState<string>("none")

  const submitNew = async () => {
    if (!newName.trim()) return
    await save.mutateAsync({
      id: null,
      body: {
        name: newName.trim(),
        parent: newParent === "none" ? null : Number(newParent),
      },
    })
    setNewName("")
    setNewParent("none")
  }

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Categorias de Produtos/Serviços</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 py-2">
          {canWrite ? (
            <div className="flex items-end gap-2 rounded-md border border-border bg-muted/30 p-2">
              <div className="flex-1">
                <Input
                  placeholder="Nome da categoria"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                />
              </div>
              <div className="w-[160px]">
                <Select value={newParent} onValueChange={setNewParent}>
                  <SelectTrigger><SelectValue placeholder="Pai (opcional)" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">— raiz —</SelectItem>
                    {(cats.data ?? []).map((c) => (
                      <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <Button size="sm" onClick={submitNew} disabled={!newName.trim() || save.isPending}>
                <Plus className="h-4 w-4" />
                Adicionar
              </Button>
            </div>
          ) : null}

          <div className="max-h-[360px] overflow-auto rounded-md border border-border">
            {cats.isLoading ? (
              <div className="p-4 text-center text-muted-foreground">Carregando…</div>
            ) : (cats.data ?? []).length === 0 ? (
              <div className="p-4 text-center text-muted-foreground">Nenhuma categoria.</div>
            ) : (
              <ul>
                {(cats.data ?? []).map((c) => (
                  <li
                    key={c.id}
                    className="flex items-center justify-between border-b border-border/40 px-3 py-2 text-[12px] last:border-b-0"
                  >
                    <div className="font-medium">{c.name}</div>
                    {canWrite ? (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          if (confirm(`Remover ${c.name}?`)) del.mutate(c.id)
                        }}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Fechar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

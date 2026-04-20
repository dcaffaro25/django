import { Construction } from "lucide-react"
import { SectionHeader } from "@/components/ui/section-header"

export function PlaceholderPage({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div>
      <SectionHeader title={title} subtitle={subtitle} />
      <div className="card-elevated flex h-[360px] flex-col items-center justify-center gap-3 text-center">
        <Construction className="h-8 w-8 text-muted-foreground" />
        <div>
          <p className="text-[14px] font-medium">Em construção</p>
          <p className="mt-0.5 text-[12px] text-muted-foreground">Esta tela será lançada em uma próxima fase.</p>
        </div>
      </div>
    </div>
  )
}

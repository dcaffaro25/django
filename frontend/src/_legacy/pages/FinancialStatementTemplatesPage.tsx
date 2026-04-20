import { PageHeader } from "@/components/layout/PageHeader"

export function FinancialStatementTemplatesPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Financial Statement Templates"
        description="Create and manage financial statement templates"
        breadcrumbs={[
          { label: "Home", href: "/" },
          { label: "Financial Statements", href: "/financial-statements" },
          { label: "Templates" },
        ]}
      />
      <div className="text-center text-muted-foreground">Coming soon...</div>
    </div>
  )
}


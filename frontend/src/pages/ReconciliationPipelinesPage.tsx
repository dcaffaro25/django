import { PageHeader } from "@/components/layout/PageHeader"

export function ReconciliationPipelinesPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Reconciliation Pipelines"
        description="Create and manage multi-stage reconciliation pipelines"
        breadcrumbs={[
          { label: "Home", href: "/" },
          { label: "Banking", href: "/banking" },
          { label: "Reconciliation Pipelines" },
        ]}
      />
      <div className="text-center text-muted-foreground">Coming soon...</div>
    </div>
  )
}


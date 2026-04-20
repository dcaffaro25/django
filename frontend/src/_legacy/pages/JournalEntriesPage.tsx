import { PageHeader } from "@/components/layout/PageHeader"

export function JournalEntriesPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Journal Entries"
        description="View and manage all journal entries"
        breadcrumbs={[
          { label: "Home", href: "/" },
          { label: "Accounting", href: "/accounting" },
          { label: "Journal Entries" },
        ]}
      />
      <div className="text-center text-muted-foreground">Coming soon...</div>
    </div>
  )
}


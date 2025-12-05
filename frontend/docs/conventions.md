# Coding Conventions & Patterns

This document outlines coding standards, naming conventions, folder structure rules, and common patterns used throughout the application.

## Naming Conventions

### Files & Folders

**Components**:
- PascalCase for component files: `TransactionForm.tsx`
- Match component name: `export function TransactionForm()`

**Hooks**:
- camelCase with `use` prefix: `use-transactions.ts`, `use-tenant.ts`
- Hook function: `export function useTransactions()`

**Utilities**:
- camelCase: `api-client.ts`, `format-currency.ts`
- Function names: `export function formatCurrency()`

**Types**:
- PascalCase: `Transaction.ts`, `types/index.ts`
- Type names: `export type Transaction = { ... }`

**Constants**:
- UPPER_SNAKE_CASE: `API_BASE_URL`, `MAX_RETRIES`

### Variables & Functions

**Variables**:
- camelCase: `const transactionId = ...`
- Boolean prefixes: `isLoading`, `hasError`, `canEdit`

**Functions**:
- camelCase: `function fetchTransactions()`
- Async functions: `async function createTransaction()`
- Event handlers: `handleSubmit`, `onClick`, `onChange`

**Components**:
- PascalCase: `function TransactionTable()`
- Props interface: `interface TransactionTableProps`

### TypeScript Types

**Interfaces**:
```typescript
interface Transaction {
  id: number
  date: string
  amount: number
}
```

**Types**:
```typescript
type TransactionStatus = 'pending' | 'posted' | 'canceled'
```

**Props**:
```typescript
interface TransactionTableProps {
  transactions: Transaction[]
  onSelect?: (transaction: Transaction) => void
}
```

## Folder Structure Rules

### Feature-Based Organization

Each major feature lives in its own folder:

```
src/features/[feature-name]/
├── components/          # Feature-specific components
├── hooks/              # Feature-specific hooks
├── api.ts              # API endpoints
├── types.ts            # Feature types
└── index.ts            # Public exports
```

**Example**:
```
src/features/transactions/
├── components/
│   ├── TransactionTable.tsx
│   ├── TransactionForm.tsx
│   └── TransactionFilters.tsx
├── hooks/
│   ├── use-transactions.ts
│   └── use-transaction-mutations.ts
├── api.ts
├── types.ts
└── index.ts
```

### Shared Components

Components used across multiple features go in `src/components/`:

```
src/components/
├── layout/              # Layout components (AppShell, Sidebar)
├── ui/                 # shadcn/ui components
└── [feature]/          # Feature-specific but shared
```

### Hooks

- Feature-specific hooks: `src/features/[feature]/hooks/`
- Shared hooks: `src/hooks/`

### Utilities

- API client: `src/lib/api-client.ts`
- Formatting: `src/lib/utils.ts`
- Constants: `src/config/constants.ts`

## UX Conventions

### When to Use Modal vs Drawer vs Page

**Modal** (Dialog):
- Quick actions: Delete confirmation, simple forms
- Small forms: 1-3 fields
- Temporary overlays that don't need much space
- Example: "Are you sure?" confirmations, quick edits

**Drawer**:
- Detail views: View transaction details, view account info
- Medium forms: 4-10 fields
- Side panels that preserve context
- Example: Transaction detail drawer, account detail drawer

**Dedicated Page**:
- Complex forms: 10+ fields, multi-step
- Full workflows: Multi-step processes
- Primary actions: Main create/edit flows
- Example: Create transaction page, reconciliation setup

### Table Patterns

**Standard Table**:
```typescript
<DataTable
  data={transactions}
  columns={columns}
  onRowClick={(row) => openDetailDrawer(row)}
  rowActions={[
    { label: 'Edit', onClick: handleEdit },
    { label: 'Delete', onClick: handleDelete },
  ]}
/>
```

**Features**:
- Sorting: Click column headers
- Filtering: Filter bar above table
- Pagination: Bottom of table
- Row selection: Checkbox column (if needed)
- Expandable rows: For nested data

### Form Patterns

**Modal Form**:
```typescript
<Dialog open={isOpen} onOpenChange={setIsOpen}>
  <DialogContent>
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)}>
        {/* Form fields */}
        <DialogFooter>
          <Button type="submit">Save</Button>
        </DialogFooter>
      </form>
    </Form>
  </DialogContent>
</Dialog>
```

**Validation**:
- Client-side: Zod schema
- Server-side: Display field errors
- Real-time: Validate on blur

### Loading States

**Skeleton Loaders** (preferred):
```typescript
{isLoading ? (
  <Skeleton className="h-10 w-full" />
) : (
  <DataTable data={data} />
)}
```

**Spinners** (for buttons):
```typescript
<Button disabled={isLoading}>
  {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
  Save
</Button>
```

### Error States

**Inline Errors**:
```typescript
{error && (
  <Alert variant="destructive">
    <AlertCircle className="h-4 w-4" />
    <AlertTitle>Error</AlertTitle>
    <AlertDescription>{error.message}</AlertDescription>
  </Alert>
)}
```

**Toast Notifications**:
```typescript
toast({
  title: "Success",
  description: "Transaction created successfully",
})
```

### Empty States

```typescript
{data.length === 0 ? (
  <div className="text-center py-12">
    <p className="text-muted-foreground">No transactions found</p>
    <Button onClick={handleCreate}>Create Transaction</Button>
  </div>
) : (
  <DataTable data={data} />
)}
```

## Code Patterns

### React Query Hooks

**Data Fetching**:
```typescript
export function useTransactions(filters?: TransactionFilters) {
  const { tenant } = useTenant()
  
  return useQuery({
    queryKey: ['transactions', tenant?.subdomain, filters],
    queryFn: () => apiClient.get(`/${tenant.subdomain}/api/transactions/`, { params: filters }),
    enabled: !!tenant,
  })
}
```

**Mutations**:
```typescript
export function useCreateTransaction() {
  const queryClient = useQueryClient()
  const { tenant } = useTenant()
  
  return useMutation({
    mutationFn: (data: CreateTransactionData) =>
      apiClient.post(`/${tenant.subdomain}/api/transactions/`, data),
    onSuccess: () => {
      queryClient.invalidateQueries(['transactions', tenant?.subdomain])
      toast({ title: "Success", description: "Transaction created" })
    },
  })
}
```

### API Client Usage

**Always include tenant**:
```typescript
// ✅ Good
apiClient.get(`/${tenant.subdomain}/api/transactions/`)

// ❌ Bad (tenant not included)
apiClient.get('/api/transactions/')
```

**Error handling**:
```typescript
try {
  const data = await apiClient.get('/api/transactions/')
} catch (error) {
  if (error.response?.status === 401) {
    // Handled by interceptor
  } else {
    toast({ title: "Error", description: error.message })
  }
}
```

### Component Structure

**Standard Component**:
```typescript
interface TransactionTableProps {
  transactions: Transaction[]
  onSelect?: (transaction: Transaction) => void
}

export function TransactionTable({ transactions, onSelect }: TransactionTableProps) {
  // Hooks
  const [selectedRow, setSelectedRow] = useState<Transaction | null>(null)
  
  // Handlers
  const handleRowClick = (transaction: Transaction) => {
    setSelectedRow(transaction)
    onSelect?.(transaction)
  }
  
  // Render
  return (
    <div>
      {/* Component JSX */}
    </div>
  )
}
```

### Type Safety

**Always type props**:
```typescript
// ✅ Good
interface Props {
  data: Transaction[]
}

// ❌ Bad
function Component({ data }: { data: any }) {
```

**Use type inference where possible**:
```typescript
// ✅ Good
const transactions: Transaction[] = await apiClient.get('/api/transactions/')

// ❌ Bad
const transactions = await apiClient.get('/api/transactions/') as any
```

## Adding a New Feature

### Step 1: Create Feature Folder

```
src/features/my-feature/
├── components/
├── hooks/
├── api.ts
├── types.ts
└── index.ts
```

### Step 2: Define Types

```typescript
// src/features/my-feature/types.ts
export interface MyFeature {
  id: number
  name: string
}
```

### Step 3: Create API Functions

```typescript
// src/features/my-feature/api.ts
import { apiClient } from '@/lib/api-client'

export async function getMyFeatures(tenant: string) {
  return apiClient.get<MyFeature[]>(`/${tenant}/api/my-features/`)
}
```

### Step 4: Create Hooks

```typescript
// src/features/my-feature/hooks/use-my-features.ts
export function useMyFeatures() {
  const { tenant } = useTenant()
  return useQuery({
    queryKey: ['my-features', tenant?.subdomain],
    queryFn: () => getMyFeatures(tenant.subdomain),
    enabled: !!tenant,
  })
}
```

### Step 5: Create Components

```typescript
// src/features/my-feature/components/MyFeatureTable.tsx
export function MyFeatureTable() {
  const { data, isLoading } = useMyFeatures()
  // ...
}
```

### Step 6: Add Route

```typescript
// src/App.tsx
<Route path="/my-feature" element={<MyFeaturePage />} />
```

### Step 7: Export from Index

```typescript
// src/features/my-feature/index.ts
export * from './components'
export * from './hooks'
export * from './types'
```

## Common Patterns

### Filter Bar Pattern

```typescript
<FilterBar
  filters={[
    { type: 'date-range', key: 'date', label: 'Date' },
    { type: 'select', key: 'status', label: 'Status', options: statusOptions },
    { type: 'search', key: 'search', label: 'Search' },
  ]}
  onFilterChange={setFilters}
/>
```

### Confirmation Dialog Pattern

```typescript
const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)

<AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
  <AlertDialogContent>
    <AlertDialogHeader>
      <AlertDialogTitle>Are you sure?</AlertDialogTitle>
      <AlertDialogDescription>
        This action cannot be undone.
      </AlertDialogDescription>
    </AlertDialogHeader>
    <AlertDialogFooter>
      <AlertDialogCancel>Cancel</AlertDialogCancel>
      <AlertDialogAction onClick={handleDelete}>Delete</AlertDialogAction>
    </AlertDialogFooter>
  </AlertDialogContent>
</AlertDialog>
```

### Optimistic Updates Pattern

```typescript
const mutation = useMutation({
  mutationFn: updateTransaction,
  onMutate: async (newData) => {
    await queryClient.cancelQueries(['transactions'])
    const previous = queryClient.getQueryData(['transactions'])
    queryClient.setQueryData(['transactions'], (old) => 
      old.map(t => t.id === newData.id ? { ...t, ...newData } : t)
    )
    return { previous }
  },
  onError: (err, newData, context) => {
    queryClient.setQueryData(['transactions'], context.previous)
  },
  onSettled: () => {
    queryClient.invalidateQueries(['transactions'])
  },
})
```

## Best Practices

1. **Always use TypeScript**: No `any` types
2. **Component composition**: Break down large components
3. **Custom hooks**: Extract reusable logic
4. **Error boundaries**: Wrap features in error boundaries
5. **Loading states**: Always show loading feedback
6. **Accessibility**: Use semantic HTML, ARIA labels
7. **Performance**: Memoize expensive computations
8. **Testing**: Write tests for critical paths (future)

## Related Documentation

- [Architecture](./architecture.md) - Overall architecture
- [Pages Overview](./pages_overview.md) - Page implementations
- [API Overview](./api_overview.md) - API patterns


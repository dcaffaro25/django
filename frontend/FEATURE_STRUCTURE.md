# Feature-Based Structure

## Overview

The application is being reorganized into a feature-based structure for better code organization, maintainability, and scalability.

## Structure

```
src/features/
├── transactions/          # Transaction management feature
│   ├── components/       # Feature-specific components
│   │   ├── TransactionDetailDrawer.tsx
│   │   └── TransactionFormModal.tsx
│   ├── hooks/           # Feature-specific hooks
│   │   └── use-transactions.ts
│   ├── api.ts           # API endpoints for this feature
│   ├── types.ts         # Feature-specific types
│   └── index.ts         # Public exports
├── accounts/             # Chart of Accounts feature
├── reconciliation/      # Bank reconciliation feature
├── financial-statements/ # Financial statements feature
└── ...
```

## Benefits

1. **Better Organization**: Related code grouped together
2. **Easier Maintenance**: Find all code for a feature in one place
3. **Reusability**: Features can be easily extracted or shared
4. **Scalability**: Easy to add new features following the same pattern
5. **Clear Boundaries**: Each feature is self-contained

## Migration Status

### ✅ Completed
- **transactions**: Fully migrated to feature structure
  - Components moved
  - Hooks moved and updated
  - API layer created
  - Types organized
  - Exports configured

### 🔄 In Progress
- **accounts**: Needs migration
- **reconciliation**: Needs migration

### 📋 Planned
- **financial-statements**
- **billing**
- **hr**
- **settings**

## Usage

### Importing from Features

```typescript
// Import hooks
import { useTransactions, useCreateTransaction } from "@/features/transactions"

// Import components
import { TransactionDetailDrawer, TransactionFormModal } from "@/features/transactions"

// Import API functions
import { getTransactions, createTransaction } from "@/features/transactions"
```

### Creating a New Feature

1. Create feature directory: `src/features/[feature-name]/`
2. Create subdirectories: `components/`, `hooks/`
3. Create files: `api.ts`, `types.ts`, `index.ts`
4. Move related code from `src/components/`, `src/hooks/`
5. Update imports throughout the app
6. Export from `index.ts`

## Feature Template

```typescript
// src/features/[feature]/api.ts
import { apiClient } from "@/lib/api-client"
import type { FeatureType } from "@/types"

export async function getFeatures(tenant: string, params?: Record<string, unknown>) {
  return apiClient.get(`/api/features/`, params)
}

// src/features/[feature]/hooks/use-features.ts
import { useQuery } from "@tanstack/react-query"
import { useTenant } from "@/providers/TenantProvider"
import * as featureApi from "../api"

export function useFeatures(params?: Record<string, unknown>) {
  const { tenant } = useTenant()
  return useQuery({
    queryKey: ["features", tenant?.subdomain, params],
    queryFn: () => featureApi.getFeatures(tenant!.subdomain, params),
    enabled: !!tenant,
  })
}

// src/features/[feature]/index.ts
export { useFeatures } from "./hooks/use-features"
export { FeatureComponent } from "./components/FeatureComponent"
export * from "./types"
export * from "./api"
```

## Migration Checklist

For each feature:
- [ ] Create feature directory structure
- [ ] Move components to `features/[feature]/components/`
- [ ] Move hooks to `features/[feature]/hooks/`
- [ ] Create `api.ts` with API functions
- [ ] Create `types.ts` for feature types
- [ ] Create `index.ts` with exports
- [ ] Update all imports throughout app
- [ ] Remove old files from `src/components/` and `src/hooks/`
- [ ] Test feature still works
- [ ] Update documentation


# Frontend API Endpoints Review

## Summary
This document reviews all frontend API calls to ensure they:
1. Properly use tenant context
2. Match backend URL patterns
3. Handle errors correctly
4. Use proper query keys for caching

## Issues Found

### 1. HR API Endpoints - Missing Trailing Slashes
**Location**: `frontend/src/features/hr/api.ts`

**Issues**:
- `/api/hr/employees` → Should be `/api/hr/employees/`
- `/api/hr/positions` → Should be `/api/hr/positions/`
- `/api/hr/timetracking` → Should be `/api/hr/timetracking/`
- `/api/hr/payrolls` → Should be `/api/hr/payrolls/`
- `/api/hr/recurring-adjustments` → Should be `/api/hr/recurring-adjustments/`

**Status**: ❌ NEEDS FIX

### 2. Settings API Endpoints - Core URLs
**Location**: `frontend/src/features/settings/api.ts`

**Analysis**: Integration and substitution rules use `/api/core/` which is mounted both:
- At root level: `/api/core/integration-rules/` (global)
- Under tenant: `/{tenant}/api/core/integration-rules/` (tenant-scoped)

**Current Implementation**: Frontend uses `/api/core/` and passes tenant. The API client interceptor adds tenant prefix, so it becomes `/{tenant}/api/core/integration-rules/` which is correct for tenant-scoped access.

**Status**: ✅ CORRECT - Using tenant-scoped endpoints as intended

### 3. Direct API Calls in Pages
**Location**: Multiple page files

**Issues**:
- `TransactionsPage.tsx` - Direct calls to `/api/entities/` and `/api/currencies/` ✅ FIXED
- `BankTransactionsPage.tsx` - Direct calls to `/api/bank_transactions/` ✅ FIXED
- `FinancialStatementsPage.tsx` - Direct calls to `/api/financial-statements/` ✅ FIXED

**Status**: ✅ FIXED

## Endpoint Categories

### ✅ Accounting Endpoints (Tenant-scoped)
All endpoints under `/{tenant}/api/`:
- `/api/accounts/` ✅
- `/api/transactions/` ✅
- `/api/currencies/` ✅
- `/api/entities/` ✅
- `/api/bank_transactions/` ✅
- `/api/reconciliation/` ✅
- `/api/reconciliation-tasks/` ✅
- `/api/reconciliation_configs/` ✅
- `/api/reconciliation-dashboard/` ✅
- `/api/financial-statements/` ✅

### ✅ HR Endpoints (Tenant-scoped)
All endpoints under `/{tenant}/api/hr/`:
- `/api/hr/employees/` ⚠️ (missing trailing slash in some calls)
- `/api/hr/positions/` ⚠️ (missing trailing slash in some calls)
- `/api/hr/timetracking/` ⚠️ (missing trailing slash in some calls)
- `/api/hr/payrolls/` ⚠️ (missing trailing slash in some calls)
- `/api/hr/recurring-adjustments/` ⚠️ (missing trailing slash in some calls)

### ✅ Billing Endpoints (Tenant-scoped)
All endpoints under `/{tenant}/api/`:
- `/api/business_partner_categories/` ✅
- `/api/business_partners/` ✅
- `/api/product_service_categories/` ✅
- `/api/product_services/` ✅
- `/api/contracts/` ✅

### ⚠️ Settings/Integration Endpoints
- `/api/core/integration-rules/` - Global or tenant? Needs verification
- `/api/core/substitution-rules/` - Global or tenant? Needs verification
- `/api/core/validate-rule/` - Global or tenant? Needs verification
- `/api/core/test-rule/` - Global or tenant? Needs verification

### ✅ Core Endpoints (Global, no tenant)
- `/api/core/companies/` ✅ (used in TenantProvider)

## Tenant Handling

### ✅ Properly Implemented
All hooks in:
- `features/accounts/hooks/use-accounts.ts` ✅
- `features/transactions/hooks/use-transactions.ts` ✅
- `features/reconciliation/hooks/use-reconciliation.ts` ✅
- `features/hr/hooks/use-hr.ts` ✅
- `features/billing/hooks/use-billing.ts` ✅
- `features/settings/hooks/use-settings.ts` ✅

All use:
- `useTenant()` hook
- `enabled: !!tenant` in queries
- Tenant subdomain in query keys
- Tenant parameter in API calls

### API Client Interceptor
The `apiClient` automatically adds tenant prefix to URLs starting with `/api/` when `tenantId` is set.

## Recommendations

1. **Fix HR API trailing slashes** - Ensure consistency
2. **Verify Settings endpoints** - Confirm if they should be tenant-scoped or global
3. **Add error boundaries** - For better error handling
4. **Add loading states** - For better UX
5. **Add retry logic** - For failed requests


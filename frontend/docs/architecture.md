# Architecture Documentation

## Overview

This React application is a modern frontend for the NORD Accounting System, built to replace the Retool implementation while preserving all functionality and improving the user experience.

## Technology Stack

- **Framework**: React 18+ with TypeScript
- **Build Tool**: Vite
- **Routing**: React Router DOM (SPA approach)
- **UI Library**: shadcn/ui components built on Radix UI
- **Styling**: Tailwind CSS
- **State Management**: 
  - React Query (TanStack Query) for server state
  - React Context for auth and theme
- **HTTP Client**: Axios
- **Form Handling**: React Hook Form with Zod validation
- **Date Handling**: date-fns

## Why SPA (Vite + React Router) vs Next.js?

We chose a **Single Page Application (SPA)** approach using Vite + React Router over Next.js for the following reasons:

1. **Simplicity**: The application is primarily a dashboard/CRUD interface that doesn't require SSR/SSG benefits
2. **API-First**: All data comes from Django REST Framework APIs, making client-side rendering ideal
3. **Deployment Flexibility**: SPA can be deployed separately from the Django backend (different origins)
4. **Development Speed**: Faster hot module replacement with Vite
5. **No SEO Requirements**: Internal business application doesn't need SEO
6. **Easier Migration**: Closer to Retool's client-side model, making migration smoother

## Application Structure

```
frontend/
├── src/
│   ├── app/                    # App-level configuration (routing, providers)
│   ├── features/               # Feature-based modules (see below)
│   ├── components/             # Shared UI components
│   │   ├── layout/            # Layout components (AppShell, Sidebar, Header)
│   │   ├── ui/                # shadcn/ui components
│   │   └── [feature]/         # Feature-specific components
│   ├── hooks/                 # Shared React hooks
│   ├── lib/                   # Utilities, API client, helpers
│   ├── types/                 # TypeScript type definitions
│   ├── config/                # Configuration, constants, env
│   └── styles/                # Global styles, Tailwind config
├── docs/                       # Documentation
└── public/                     # Static assets
```

## Feature-Based Structure

Each major feature is organized as a self-contained module:

```
src/features/[feature-name]/
├── components/                 # Feature-specific components
│   ├── [Feature]Table.tsx
│   ├── [Feature]Form.tsx
│   ├── [Feature]DetailDrawer.tsx
│   └── [Feature]Filters.tsx
├── hooks/                     # Feature-specific hooks
│   ├── use-[feature].ts      # Data fetching hooks
│   └── use-[feature]-mutations.ts
├── api.ts                     # API endpoints and types
├── types.ts                   # Feature-specific types
└── index.ts                   # Public exports
```

**Example Features:**
- `transactions` - Transaction management
- `reconciliation` - Bank reconciliation
- `accounts` - Chart of Accounts
- `financial-statements` - Financial reporting
- `hr` - Human resources
- `billing` - Business partners, products, contracts
- `settings` - Configuration and rules

## Data Flow: Frontend ↔ Django DRF API

### Authentication Flow

1. **Login**:
   ```
   POST /login/
   Body: { username, password }
   Response: { token, user: {...} }
   ```
   - Token stored in localStorage
   - User data stored in React Context

2. **API Requests**:
   - All requests include: `Authorization: Token {token}`
   - Tenant context included in URL: `/{tenant_subdomain}/api/...`
   - Token automatically added via Axios interceptor

3. **Token Refresh**:
   - Currently tokens don't expire (DRF TokenAuthentication)
   - If token becomes invalid, user redirected to login

### Multi-Tenancy Flow

1. **Tenant Selection**:
   - User selects tenant from dropdown in sidebar
   - Tenant subdomain stored in React Context
   - All subsequent API calls include tenant in URL path

2. **API Request Pattern**:
   ```
   GET /{tenant_subdomain}/api/transactions/
   Headers: { Authorization: Token {token} }
   ```

3. **Backend Processing**:
   - `TenantMiddleware` extracts tenant from URL path
   - `ScopedQuerysetMixin` filters queryset by tenant
   - Data automatically scoped to selected tenant

### Data Fetching Pattern

1. **React Query Hooks**:
   ```typescript
   const { data, isLoading, error } = useTransactions({
     status: 'pending',
     tenant: currentTenant
   })
   ```

2. **API Client**:
   ```typescript
   apiClient.get(`/${tenant}/api/transactions/`, { params })
   ```

3. **Caching & Refetching**:
   - React Query handles caching automatically
   - Stale time: 30 seconds (configurable per query)
   - Automatic refetch on window focus
   - Manual refetch after mutations

## State Management

### Server State (React Query)

- All API data managed by React Query
- Automatic caching, refetching, and error handling
- Optimistic updates for mutations

### Client State

- **Auth State**: React Context (`AuthProvider`)
- **Theme State**: React Context (`ThemeProvider`)
- **Tenant State**: React Context (`TenantProvider`)
- **Form State**: React Hook Form (local component state)
- **UI State**: React useState/useReducer (modals, drawers, etc.)

## Routing

### Route Structure

```
/                                    → Redirect to /accounting/transactions
/login                               → Login page

/accounting/
  ├── transactions                   → Transaction list
  ├── journal-entries                → Journal entries
  └── accounts                       → Chart of Accounts

/banking/
  ├── bank-transactions             → Bank transactions
  ├── reconciliation-dashboard      → Reconciliation overview
  ├── reconciliation-tasks          → Reconciliation tasks
  ├── reconciliation-configs        → Reconciliation configurations
  └── reconciliation-pipelines       → Reconciliation pipelines

/financial-statements/
  ├── statements                    → Financial statements
  └── templates                     → Statement templates

/hr/                                → HR module (future)
/billing/                           → Billing module (future)
/settings/                          → Settings (future)
```

### Route Protection

- Private routes wrapped in `<PrivateRoute>` component
- Checks for valid token in localStorage
- Redirects to `/login` if not authenticated

## Theming & Multi-Tenancy

See [theming_and_tenancy.md](./theming_and_tenancy.md) for detailed information.

**High-level flow:**
1. App loads → Fetch tenant list
2. User selects tenant → Fetch tenant branding (if available)
3. Apply theme via CSS variables and Tailwind config
4. Fallback to default platform theme if no tenant branding

## Error Handling

### API Errors

- **401 Unauthorized**: Redirect to login
- **403 Forbidden**: Show error message, hide restricted actions
- **404 Not Found**: Show "Not Found" message
- **500 Server Error**: Show generic error with retry option
- **Validation Errors**: Display field-level errors in forms

### Error Boundaries

- Top-level `<ErrorBoundary>` catches React errors
- Feature-level error boundaries for isolated failures
- Graceful degradation with error messages

## Performance Optimizations

1. **Code Splitting**: 
   - Route-based code splitting (React.lazy)
   - Feature-based code splitting

2. **Data Fetching**:
   - React Query caching reduces redundant requests
   - Pagination for large datasets
   - Virtual scrolling for long lists (future)

3. **Bundle Optimization**:
   - Tree shaking
   - Vite's automatic code splitting
   - Dynamic imports for heavy components

4. **UI Optimizations**:
   - Skeleton loaders instead of spinners
   - Optimistic updates for better perceived performance
   - Debounced search/filter inputs

## Security Considerations

1. **Token Storage**: localStorage (consider httpOnly cookies for production)
2. **XSS Protection**: React's automatic escaping, sanitize user inputs
3. **CSRF**: Handled by Django backend (CSRF middleware)
4. **CORS**: Configured on Django backend
5. **Input Validation**: Client-side (Zod) + Server-side (Django serializers)

## Development Workflow

1. **Local Development**:
   ```bash
   npm run dev
   # Frontend runs on http://localhost:5173
   # API calls to http://localhost:8000 (or VITE_API_BASE_URL)
   ```

2. **Environment Variables**:
   ```env
   VITE_API_BASE_URL=http://localhost:8000
   ```

3. **Building for Production**:
   ```bash
   npm run build
   # Output in dist/
   ```

## Deployment

### Separate Frontend Deployment

1. Build frontend: `npm run build`
2. Deploy `dist/` to static hosting (Vercel, Netlify, S3, etc.)
3. Configure CORS on Django backend
4. Set `VITE_API_BASE_URL` to production API URL

### Integrated Deployment (Optional)

- Django can serve static files from `dist/`
- Configure Django to serve React app for all non-API routes
- Single deployment, but less flexible

## Future Considerations

1. **SSR/SSG**: If needed, consider migrating to Next.js
2. **Real-time Updates**: WebSocket integration for live data
3. **Offline Support**: Service workers, PWA features
4. **Mobile App**: React Native using shared business logic
5. **Micro-frontends**: If application grows significantly

## Related Documentation

- [API Overview](./api_overview.md) - API endpoints and integration
- [Pages Overview](./pages_overview.md) - Page-by-page documentation
- [Theming & Tenancy](./theming_and_tenancy.md) - Multi-tenant theming
- [Conventions](./conventions.md) - Coding standards and patterns


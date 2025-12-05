# Theming & Multi-Tenancy

This document explains how multi-tenancy and theming work in the application.

## Multi-Tenancy Overview

The NORD Accounting System supports multiple tenants (companies) in a single application instance. Each tenant has:
- Isolated data (scoped by `company` foreign key)
- Optional custom branding/theme
- User access restricted to their tenant (unless superuser)

## Tenant Identification

### URL Path-Based Routing

Tenants are identified via **URL path prefix**:

```
/{tenant_subdomain}/api/...
```

**Example:**
```
GET /acme-corp/api/transactions/
GET /globex/api/transactions/
```

### How It Works

1. **Frontend**: User selects tenant from dropdown in sidebar
2. **API Client**: Automatically prepends tenant subdomain to all API URLs
3. **Backend Middleware**: `TenantMiddleware` extracts tenant from URL path
4. **Backend Viewsets**: `ScopedQuerysetMixin` filters queryset by tenant

### Tenant Selection Flow

```typescript
// User selects tenant in sidebar
setTenant('acme-corp')

// API client automatically includes tenant in URL
apiClient.get('/api/transactions/')
// → GET /acme-corp/api/transactions/
```

## Current Implementation

### Backend (Django)

**Tenant Model**: `multitenancy.Company`
```python
class Company(BaseModel):
    name = models.CharField(max_length=100, unique=True)
    subdomain = models.CharField(max_length=100, unique=True)
    # No branding fields yet
```

**Tenant Middleware**: `multitenancy.middleware.TenantMiddleware`
- Extracts tenant from URL path
- Validates tenant exists
- Sets `request.tenant` for queryset filtering

**Queryset Scoping**: `ScopedQuerysetMixin`
- Automatically filters queryset by `company=request.tenant`
- Superusers can see all tenants (or specific tenant if selected)

### Frontend (React)

**Current State**:
- Tenant selection in sidebar dropdown
- API client includes tenant in URL path
- No tenant-specific theming yet

**Future State** (to be implemented):
- ThemeProvider fetches tenant branding
- CSS variables updated based on tenant theme
- Fallback to default platform theme

## Branding & Theming

### Current Status

**⚠️ Not Yet Implemented**: The backend `Company` model doesn't have branding fields yet.

### Proposed Implementation

#### Backend Changes (Future)

Add branding fields to `Company` model:

```python
class Company(BaseModel):
    name = models.CharField(max_length=100, unique=True)
    subdomain = models.CharField(max_length=100, unique=True)
    
    # Branding fields
    primary_color = models.CharField(max_length=7, default='#025736')  # Hex color
    secondary_color = models.CharField(max_length=7, default='#025736')
    logo_url = models.URLField(blank=True, null=True)
    favicon_url = models.URLField(blank=True, null=True)
    custom_css = models.TextField(blank=True, null=True)
```

**API Endpoint** (to be created):
```http
GET /api/core/companies/{id}/branding/
```

**Response:**
```json
{
  "primary_color": "#025736",
  "secondary_color": "#025736",
  "logo_url": "https://cdn.example.com/logos/acme.png",
  "favicon_url": "https://cdn.example.com/favicons/acme.ico",
  "custom_css": "..."
}
```

#### Frontend Implementation (Future)

**ThemeProvider Component**:

```typescript
// src/providers/ThemeProvider.tsx
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const { tenant } = useTenant()
  const { data: branding } = useQuery({
    queryKey: ['tenant-branding', tenant?.id],
    queryFn: () => apiClient.get(`/api/core/companies/${tenant.id}/branding/`),
    enabled: !!tenant?.id,
  })

  useEffect(() => {
    if (branding) {
      // Update CSS variables
      document.documentElement.style.setProperty('--primary', branding.primary_color)
      document.documentElement.style.setProperty('--secondary', branding.secondary_color)
      // Update favicon
      if (branding.favicon_url) {
        // Update favicon link
      }
    } else {
      // Fallback to default theme
      document.documentElement.style.setProperty('--primary', '#025736')
      document.documentElement.style.setProperty('--secondary', '#025736')
    }
  }, [branding])

  return <>{children}</>
}
```

**Tailwind Config Integration**:

```javascript
// tailwind.config.js
module.exports = {
  theme: {
    extend: {
      colors: {
        primary: 'var(--primary)',
        secondary: 'var(--secondary)',
      },
    },
  },
}
```

**CSS Variables**:

```css
/* src/index.css */
:root {
  --primary: #025736;
  --secondary: #025736;
  --background: #ffffff;
  --foreground: #0d0d0d;
  /* ... other theme tokens */
}
```

## Default Platform Theme

When no tenant branding is available, the app uses the default platform theme:

- **Primary Color**: `#025736` (Green)
- **Secondary Color**: `#025736`
- **Success Color**: `#059669`
- **Danger Color**: `#dc2626`
- **Warning Color**: `#cd6f00`
- **Info Color**: `#3170f9`

These match the Retool app theme.

## Tenant Switching

### User Flow

1. User clicks tenant dropdown in sidebar
2. Selects new tenant
3. App updates:
   - Tenant context in React state
   - API client tenant prefix
   - Theme (if branding available)
   - Refetches data for new tenant

### Implementation

```typescript
// src/hooks/use-tenant.ts
export function useTenant() {
  const [tenant, setTenant] = useState<Company | null>(null)
  
  const switchTenant = (tenantSubdomain: string) => {
    // Update API client
    apiClient.setTenantId(tenantSubdomain)
    
    // Update React state
    setTenant({ subdomain: tenantSubdomain })
    
    // Refetch tenant branding
    queryClient.invalidateQueries(['tenant-branding'])
    
    // Refetch all data
    queryClient.invalidateQueries()
  }
  
  return { tenant, switchTenant }
}
```

## Superuser Access

Superusers can:
- See all tenants (when tenant is set to "all")
- Switch between tenants
- Access admin endpoints

**Backend Behavior**:
- If `request.user.is_superuser` and `request.tenant == 'all'`: No filtering
- If `request.user.is_superuser` and `request.tenant == Company`: Filter by that tenant
- If regular user: Always filter by their tenant

## Tenant Data Isolation

### Automatic Scoping

All tenant-aware models automatically filter by `company`:

```python
# Backend
class Transaction(TenantAwareBaseModel):
    company = models.ForeignKey(Company, ...)
    # ... other fields

# ViewSet automatically filters:
queryset = Transaction.objects.filter(company=request.tenant)
```

### Frontend Considerations

- Always include tenant in API URLs
- Don't mix data from different tenants
- Clear cache when switching tenants
- Validate tenant context before API calls

## Future Enhancements

1. **Branding API**: Add branding endpoints to backend
2. **Theme Editor**: Admin interface to customize tenant themes
3. **Logo Upload**: File upload for tenant logos
4. **Custom CSS**: Allow tenants to inject custom CSS
5. **White-labeling**: Full white-label support for enterprise tenants

## Related Documentation

- [Architecture](./architecture.md) - Overall architecture
- [API Overview](./api_overview.md) - API endpoints
- [Conventions](./conventions.md) - Implementation patterns


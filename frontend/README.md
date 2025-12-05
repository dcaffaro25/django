# NORD Accounting System - Frontend

A modern React + TypeScript frontend application built with Vite, shadcn/ui, and React Query. This application replaces the Retool implementation while preserving all functionality and improving the user experience.

## Features

- **Modern Stack**: React 18, TypeScript, Vite
- **UI Components**: shadcn/ui components built on Radix UI
- **State Management**: React Query (TanStack Query) for server state
- **Routing**: React Router v6 (SPA approach)
- **Styling**: Tailwind CSS
- **Form Handling**: React Hook Form with Zod validation
- **Multi-Tenancy**: Full support for multiple tenants with isolated data
- **Authentication**: DRF TokenAuthentication

## Getting Started

### Prerequisites

- Node.js 18+ and npm/yarn/pnpm
- Django backend running (see main project README)

### Installation

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

### Environment Variables

Create a `.env` file in the frontend directory:

```env
VITE_API_BASE_URL=http://localhost:8000
```

**Production**: Set `VITE_API_BASE_URL` to your production API URL.

## Project Structure

```
frontend/
├── src/
│   ├── components/          # React components
│   │   ├── ui/             # shadcn/ui components
│   │   ├── layout/         # Layout components (AppShell, Sidebar, Header)
│   │   └── [feature]/      # Feature-specific components
│   ├── features/           # Feature-based modules (future structure)
│   ├── hooks/              # Custom React hooks
│   ├── lib/                # Utilities and API client
│   ├── types/              # TypeScript type definitions
│   ├── pages/              # Page components
│   ├── config/             # Configuration and constants
│   └── App.tsx             # Main app component
├── docs/                   # Documentation
│   ├── architecture.md     # Architecture overview
│   ├── api_overview.md     # API endpoints
│   ├── pages_overview.md   # Page documentation
│   ├── theming_and_tenancy.md  # Multi-tenant theming
│   └── conventions.md      # Coding standards
├── public/                 # Static assets
└── package.json
```

## API Integration

The app uses a centralized API client (`src/lib/api-client.ts`) that:

- **Authentication**: Uses DRF TokenAuthentication (`Token {token}` header)
- **Multi-Tenancy**: Automatically includes tenant subdomain in URL path
- **Error Handling**: Automatic 401 handling with redirect to login
- **Type Safety**: Fully typed API responses

### Authentication Flow

1. User logs in via `POST /login/`
2. Backend returns `{ token, user }`
3. Token stored in localStorage as `auth_token`
4. All subsequent requests include: `Authorization: Token {token}`
5. Tenant included in URL: `/{tenant_subdomain}/api/...`

### Example API Call

```typescript
import { apiClient } from '@/lib/api-client'

// Set tenant
apiClient.setTenantId('acme-corp')

// Make request (tenant automatically included)
const transactions = await apiClient.get('/api/transactions/')
// → GET /acme-corp/api/transactions/
// → Headers: { Authorization: Token {token} }
```

## Multi-Tenancy

The application supports multiple tenants (companies):

1. **Tenant Selection**: Dropdown in sidebar
2. **Data Isolation**: All data automatically scoped to selected tenant
3. **URL Pattern**: `/{tenant_subdomain}/api/...`
4. **Theme Support**: Future support for tenant-specific branding

See [docs/theming_and_tenancy.md](./docs/theming_and_tenancy.md) for details.

## Development

### Running the App

```bash
npm run dev
```

Frontend runs on `http://localhost:5173` (Vite default).

### API Configuration

Ensure your Django backend is running and accessible at the URL specified in `VITE_API_BASE_URL`.

### Code Style

- TypeScript strict mode enabled
- ESLint for code quality
- Prettier for formatting (recommended)
- Follow conventions in [docs/conventions.md](./docs/conventions.md)

## Documentation

Comprehensive documentation is available in the `docs/` directory:

- **[Architecture](./docs/architecture.md)**: Overall architecture, technology choices, data flow
- **[API Overview](./docs/api_overview.md)**: All API endpoints and usage patterns
- **[Pages Overview](./docs/pages_overview.md)**: Page-by-page documentation
- **[Theming & Tenancy](./docs/theming_and_tenancy.md)**: Multi-tenant architecture and theming
- **[Conventions](./docs/conventions.md)**: Coding standards and patterns

## UI/UX Principles

The app follows these design principles:

- **Modal-first**: Quick add/edit actions use modals
- **Drawer-based details**: Detail views use side drawers
- **Table-centric**: Primary data display method
- **Progressive disclosure**: Expandable rows, collapsible sections
- **Context preservation**: Maintains context during navigation
- **Clear feedback**: Loading states, error messages, success toasts

## Features Status

### ✅ Implemented

- Authentication & Login
- Transactions Management
- Bank Transactions
- Reconciliation Dashboard
- Reconciliation Tasks
- Reconciliation Configs
- Chart of Accounts
- Financial Statements (basic)

### ⚠️ Partial

- Journal Entries
- Reconciliation Pipelines
- Financial Statement Templates

### ❌ Not Yet Implemented

- Billing Module (Business Partners, Products, Contracts)
- HR Module (Employees, Time Tracking, Payroll)
- Settings/Configuration (Integration Rules)
- Home/Dashboard
- AI Chat Integration

See [docs/pages_overview.md](./docs/pages_overview.md) for detailed status.

## Migration from Retool

This application is a complete migration from Retool. All Retool functionality is being preserved:

- ✅ All pages mapped to React routes
- ✅ All API endpoints integrated
- ✅ All workflows preserved
- ✅ Improved UX and performance

See [RETOOL_UI_UX_ANALYSIS.md](./RETOOL_UI_UX_ANALYSIS.md) for detailed Retool analysis.

## Building for Production

```bash
npm run build
```

Output is in `dist/` directory. Deploy to any static hosting service:

- Vercel
- Netlify
- AWS S3 + CloudFront
- Azure Static Web Apps
- Or serve from Django (configure Django to serve static files)

### Environment Variables for Production

Set `VITE_API_BASE_URL` to your production API URL before building:

```bash
VITE_API_BASE_URL=https://api.example.com npm run build
```

## Troubleshooting

### CORS Issues

Ensure Django backend has CORS configured:

```python
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "https://your-frontend-domain.com",
]
```

### Authentication Issues

- Verify token is stored as `auth_token` in localStorage
- Check that `Authorization: Token {token}` header is sent
- Ensure backend `/login/` endpoint is accessible

### Tenant Issues

- Verify tenant subdomain is correct
- Check that tenant exists in database
- Ensure API URLs include tenant: `/{tenant}/api/...`

## Contributing

1. Follow coding conventions in [docs/conventions.md](./docs/conventions.md)
2. Add documentation for new features
3. Write TypeScript types for all API responses
4. Use React Query for all data fetching
5. Follow UI/UX principles outlined in documentation

## License

Proprietary - NORD Accounting System

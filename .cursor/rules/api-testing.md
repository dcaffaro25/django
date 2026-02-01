# API Testing Reference

When testing Nord backend APIs:
- **Do not make code changes.** Use existing endpoints only—call them, inspect responses, and report findings. Do not modify views, serializers, or other application code.
- Use `mcp_web_fetch` or run scripts/curl to call the API directly.

## Base Configuration

| Setting | Value |
|---------|-------|
| **Base URL** | `https://server-production-e754.up.railway.app` |
| **Auth Header** | `Authorization: Token d7a149593414019fb57a43f1cbb333e17179b937` |

## Tenants

| Tenant | company_id | tenant_id (URL path) |
|--------|------------|----------------------|
| **datbaby** | 4 | `4` or `datbaby` |
| **evolat** | 5 | `5` or `evolat` |

## Key Endpoints

- **Companies**: `GET /api/core/companies/?format=json`
- **Accounts**: `GET /{tenant_id}/api/accounts/?format=json`
- **ERP connections**: `GET /{tenant_id}/api/connections/`
- **Income statement**: `POST /{tenant_id}/api/financial-statements/detailed_income_statement/`

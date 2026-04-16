# 04 — Multi-Tenancy e Usuários

## 4.1 Conceito de Multi-Tenancy

A plataforma Nord opera em modo **multi-tenant**: uma única instalação serve múltiplas empresas, cada uma com seus dados isolados.

### Como Funciona

1. Cada empresa possui um **subdomínio** único (ex: `acme`, `grupo-xyz`)
2. Todas as URLs de negócio são prefixadas: `/{subdominio}/api/...`
3. O middleware resolve o tenant pelo primeiro segmento da URL
4. Todos os dados são filtrados automaticamente pela empresa do contexto

```
Requisição: GET /acme/api/transactions/
                 ^^^^
                 └─ tenant_id = "acme" → Company(subdomain="acme")
```

### Tenant "all" (Superusuários)

Superusuários podem acessar dados de **todas as empresas** usando o tenant especial `all`:

```bash
GET /all/api/transactions/   # Todas as transações de todas as empresas
GET /all/api/accounts/       # Todas as contas de todas as empresas
```

> **Atenção:** O tenant `all` é restrito a superusuários. Usuários normais receberão erro 403.

---

## 4.2 Empresas (Companies)

### Criando uma Empresa

**Via Admin:** Admin → Multitenancy → Companies → "Add Company"

**Via API:**
```bash
POST /api/core/companies/
{
  "name": "Acme Ltda",
  "subdomain": "acme"
}
```

**Campos:**

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `name` | string | Sim | Nome da empresa (único) |
| `subdomain` | string | Sim | Identificador URL (único, sem espaços) |

### Listando Empresas

```bash
GET /api/core/companies/
```

### Resumo de Conciliação por Empresa

```bash
GET /api/core/companies/{id}/reconciliation-summary/
```

Retorna métricas de conciliação agregadas para a empresa.

---

## 4.3 Entidades (Entities)

Entidades representam a **estrutura organizacional** dentro de cada empresa: filiais, departamentos, centros de negócio, etc.

### Estrutura em Árvore

As entidades formam uma hierarquia (MPTT — Modified Preorder Tree Traversal):

```
Grupo ABC (empresa)
├── ABC Holding
│   ├── ABC Industrial
│   │   ├── Fábrica São Paulo
│   │   └── Fábrica Minas
│   └── ABC Comercial
│       ├── Loja Centro
│       └── Loja Shopping
└── ABC Serviços
    └── Consultoria
```

### Criando Entidades

**Via Admin:** Admin → Multitenancy → Entities → "Add Entity"

**Via API:**
```bash
POST /acme/api/entities/
{
  "name": "Fábrica São Paulo",
  "parent": 2,
  "inherit_accounts": true,
  "inherit_cost_centers": true
}
```

**Campos:**

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `name` | string | Sim | Nome da entidade |
| `parent` | integer | Não | ID da entidade-pai |
| `cliente_erp_id` | string | Não | Identificador no ERP externo |
| `inherit_accounts` | boolean | Não | Herdar contas contábeis do pai (padrão: `false`) |
| `inherit_cost_centers` | boolean | Não | Herdar centros de custo do pai (padrão: `false`) |

### Herança de Contas e Centros de Custo

Quando `inherit_accounts = true`:
- A entidade tem acesso a **todas as contas da entidade-pai** além das suas próprias
- Útil para filiais que compartilham o plano de contas da holding

Quando `inherit_cost_centers = true`:
- A entidade herda os centros de custo do pai

### Endpoints de Entidades

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/{tenant}/api/entities/` | Listar entidades |
| `POST` | `/{tenant}/api/entities/` | Criar entidade |
| `GET` | `/{tenant}/api/entities/{id}/` | Detalhe da entidade |
| `PUT/PATCH` | `/{tenant}/api/entities/{id}/` | Atualizar |
| `DELETE` | `/{tenant}/api/entities/{id}/` | Excluir |
| `GET` | `/{tenant}/api/entities/{id}/context-options/` | Opções de contexto (contas, centros de custo efetivos) |
| `GET` | `/{tenant}/api/entities/{id}/effective-context/` | Contexto efetivo com herança resolvida |
| `GET` | `/{tenant}/api/entities-mini/` | Lista compacta (apenas id e nome) |

### Visualização em Árvore

```bash
GET /acme/entity-tree/{company_id}/
```

Retorna a árvore completa de entidades para uma empresa.

---

## 4.4 Usuários

### Criando Usuários

**Via Admin:** Admin → Multitenancy → Users → "Add User"

**Via API:**
```bash
POST /api/core/users/create/
{
  "username": "maria.silva",
  "password": "senha_segura_123",
  "email": "maria@empresa.com",
  "first_name": "Maria",
  "last_name": "Silva"
}
```

### Campos do Usuário

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `username` | string | Login do usuário (único) |
| `password` | string | Senha (mínimo definido pelo Django) |
| `email` | string | Email do usuário |
| `first_name` / `last_name` | string | Nome completo |
| `is_staff` | boolean | Pode acessar o Django Admin |
| `is_superuser` | boolean | Acesso total (inclusive tenant `all`) |
| `is_active` | boolean | Conta ativa |
| `must_change_password` | boolean | Forçar troca de senha no próximo login |

### Tipos de Usuário

| Tipo | `is_staff` | `is_superuser` | Acesso |
|------|-----------|----------------|--------|
| **Operador** | `false` | `false` | API e frontend apenas |
| **Administrador** | `true` | `false` | API, frontend e admin (permissões por grupo) |
| **Superusuário** | `true` | `true` | Acesso total, incluindo tenant `all` |

### Endpoints de Usuários

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/api/core/users/` | Listar usuários |
| `POST` | `/api/core/users/create/` | Criar usuário |
| `GET` | `/api/core/users/{id}/` | Detalhe |
| `PUT/PATCH` | `/api/core/users/{id}/` | Atualizar |
| `POST` | `/change-password/` | Alterar senha própria |
| `POST` | `/reset-password/` | Solicitar reset de senha |
| `POST` | `/force-reset-password/` | Reset forçado (admin) |

---

## 4.5 Autenticação

### Token Authentication (Padrão)

O método principal de autenticação é o **DRF Token**:

```bash
# 1. Obter token via login
POST /login/
{"username": "maria", "password": "senha123"}
→ {"token": "abc123..."}

# 2. Usar o token em todas as requisições
GET /acme/api/transactions/
Authorization: Token abc123...
```

O token é **persistente** — não expira automaticamente. Para invalidar, use o logout:

```bash
POST /logout/
Authorization: Token abc123...
```

### JWT (Alternativo)

Endpoints JWT estão disponíveis mas **não são o método padrão**:

```bash
# Obter par de tokens JWT
POST /api/token/
{"username": "maria", "password": "senha123"}
→ {"access": "eyJ...", "refresh": "eyJ..."}

# Renovar token de acesso
POST /api/token/refresh/
{"refresh": "eyJ..."}
→ {"access": "eyJ..."}
```

> **Dica:** Para integrações simples, use o Token Authentication. Para aplicações com múltiplos clientes simultâneos, considere JWT.

---

## 4.6 Permissões e Segurança

### Flag AUTH_OFF (Ambiente de Desenvolvimento)

Em desenvolvimento, a flag `AUTH_OFF = True` pode desabilitar autenticação em todos os ViewSets. Em produção, **esta flag deve ser `False`**.

### CORS e CSRF

A plataforma gerencia origens confiáveis para CORS e CSRF:

- **Origens confiáveis** são configuradas em `settings.py` via `CSRF_TRUSTED_ORIGINS` e `CORS_ALLOWED_ORIGINS`
- Em modo `DEBUG`, todas as origens são permitidas para facilitar o desenvolvimento
- Ao adicionar um novo frontend ou aplicação, adicione a URL às origens confiáveis

### Boas Práticas

1. **Nunca compartilhe tokens** entre usuários
2. **Use HTTPS** em produção
3. **Crie usuários com o mínimo de permissões** necessário
4. **Revogue tokens** de usuários inativos
5. **Monitore o feed de atividades** para auditoria:

```bash
GET /api/activity/?page_size=50
```

---

## 4.7 Uso Avançado: Importação em Massa de Dados

### Bulk Import

Para importar grandes volumes de registros:

```bash
POST /api/core/bulk-import/
{
  "model": "Transaction",
  "records": [
    {"entity": 1, "date": "2026-01-15", "amount": 1000, "currency": 1, "description": "..."},
    {"entity": 1, "date": "2026-01-16", "amount": 2500, "currency": 1, "description": "..."}
  ]
}
```

### Preview antes de Importar

```bash
POST /api/core/bulk-import-preview/
{
  "model": "Transaction",
  "records": [...]
}
```

Retorna o que seria criado/atualizado sem persistir.

### Merge de Registros

Para mesclar registros duplicados:

```bash
POST /api/core/merge-records/
{
  "model": "BusinessPartner",
  "keep_id": 1,
  "merge_ids": [2, 3, 4]
}
```

---

*Anterior: [03 — Painel Administrativo](03-admin-django.md) · Próximo: [05 — Contabilidade](05-contabilidade.md)*

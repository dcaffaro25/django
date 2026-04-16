# 02 — Primeiros Passos

## 2.1 Acessando a Plataforma

### Login via Interface Web

1. Acesse `https://servidor.com/login/` no navegador
2. Insira seu **usuário** e **senha**
3. Após o login, você será redirecionado para o painel da sua empresa

### Login via API

Para integrações programáticas, faça uma chamada POST:

```bash
curl -X POST https://servidor.com/login/ \
  -H "Content-Type: application/json" \
  -d '{"username": "seu_usuario", "password": "sua_senha"}'
```

**Resposta de sucesso:**

```json
{
  "token": "abc123def456ghi789...",
  "user_id": 1,
  "username": "seu_usuario",
  "is_superuser": false
}
```

> **Dica:** Guarde o token retornado — ele será usado em todas as requisições seguintes.

### Usando o Token

Inclua o token no cabeçalho `Authorization` de cada requisição:

```bash
curl -H "Authorization: Token abc123def456ghi789..." \
  https://servidor.com/acme/api/transactions/
```

---

## 2.2 Entendendo a Navegação

### URLs com Tenant

Quase todos os endpoints de negócio são prefixados com o **identificador da empresa** (tenant). Se sua empresa tem o subdomínio `acme`, as URLs ficam:

```
https://servidor.com/acme/api/transactions/
https://servidor.com/acme/api/accounts/
https://servidor.com/acme/api/bank-accounts/
```

> **Atenção:** Se você é superusuário, pode usar `all` como tenant para acessar dados de todas as empresas: `https://servidor.com/all/api/transactions/`

### Endpoints Globais (sem tenant)

Alguns endpoints não dependem de uma empresa específica:

| Endpoint | Descrição |
|----------|-----------|
| `POST /login/` | Autenticação |
| `POST /logout/` | Encerrar sessão |
| `/api/core/users/` | Gestão de usuários |
| `/api/core/companies/` | Gestão de empresas |
| `/api/core/financial_indices/` | Índices financeiros |
| `/api/meta/endpoints/` | Lista de todos os endpoints |
| `/api/meta/models/` | Catálogo de modelos de dados |
| `/api/meta/health/` | Verificação de saúde do sistema |

---

## 2.3 Operações Básicas com a API

### Listagem com Paginação

Todas as listagens são paginadas. A resposta inclui:

```json
{
  "count": 245,
  "next": "https://servidor.com/acme/api/transactions/?page=2",
  "previous": null,
  "results": [...]
}
```

| Parâmetro | Descrição | Exemplo |
|-----------|-----------|---------|
| `page` | Número da página | `?page=2` |
| `page_size` | Itens por página | `?page_size=50` |

### Filtros

A maioria dos endpoints aceita filtros via query string:

```bash
# Transações de uma entidade específica, no mês de março
GET /acme/api/transactions/?entity=5&date_after=2026-03-01&date_before=2026-03-31

# Contas bancárias ativas
GET /acme/api/bank-accounts/?is_active=true

# Busca por texto em descrição
GET /acme/api/transactions/?search=pagamento+fornecedor
```

### Ordenação

Use o parâmetro `ordering` para ordenar resultados:

```bash
# Transações mais recentes primeiro
GET /acme/api/transactions/?ordering=-date

# Contas por código
GET /acme/api/accounts/?ordering=account_code
```

> **Dica:** Prefixe com `-` para ordem decrescente.

### Criação (POST)

```bash
curl -X POST https://servidor.com/acme/api/transactions/ \
  -H "Authorization: Token seu_token" \
  -H "Content-Type: application/json" \
  -d '{
    "entity": 1,
    "date": "2026-04-15",
    "amount": 1500.00,
    "currency": 1,
    "description": "Pagamento de fornecedor"
  }'
```

### Atualização (PUT / PATCH)

```bash
# Atualização parcial (PATCH) — apenas os campos que mudam
curl -X PATCH https://servidor.com/acme/api/transactions/42/ \
  -H "Authorization: Token seu_token" \
  -H "Content-Type: application/json" \
  -d '{"description": "Pagamento fornecedor — NF 12345"}'
```

### Exclusão (DELETE)

```bash
curl -X DELETE https://servidor.com/acme/api/transactions/42/ \
  -H "Authorization: Token seu_token"
```

---

## 2.4 Gestão de Senha

### Alterar Senha Própria

```bash
POST /change-password/
{
  "old_password": "senha_atual",
  "new_password": "nova_senha"
}
```

### Reset de Senha (Administrador)

Administradores podem forçar o reset de senha de outro usuário:

```bash
POST /force-reset-password/
{
  "user_id": 5,
  "new_password": "senha_temporaria"
}
```

> **Dica:** Ao usar `force-reset-password`, o campo `must_change_password` do usuário é ativado automaticamente.

---

## 2.5 Descobrindo a API

A plataforma possui uma **camada de introspecção** que permite descobrir todos os endpoints e modelos disponíveis.

### Listar Todos os Endpoints

```bash
GET /api/meta/endpoints/
```

Retorna cada endpoint com método HTTP, caminho, parâmetros, serializador, filtros e campos de busca.

### Explorar Modelos de Dados

```bash
# Lista todos os modelos
GET /api/meta/models/

# Detalhes de um modelo específico
GET /api/meta/models/Transaction/

# Relacionamentos de um modelo
GET /api/meta/models/Transaction/relationships/
```

### Listar Enums e Filtros

```bash
# Valores possíveis para campos do tipo choice/enum
GET /api/meta/enums/

# Filtros disponíveis por endpoint
GET /api/meta/filters/
```

### Verificar Saúde do Sistema

```bash
GET /api/meta/health/
```

Retorna status do sistema, versão da API e timestamp (não requer autenticação).

---

## 2.6 Checklist de Configuração Inicial

Para começar a usar a plataforma, siga esta ordem:

| Passo | Ação | Onde fazer |
|-------|------|-----------|
| 1 | Criar a empresa (Company) | Admin → Companies |
| 2 | Criar usuários | Admin → Users ou `POST /api/core/users/create/` |
| 3 | Criar entidades (filiais, departamentos) | Admin → Entities ou API |
| 4 | Importar plano de contas | ETL ou Admin → Accounts |
| 5 | Cadastrar bancos e contas bancárias | Admin ou API |
| 6 | Configurar moedas | Admin → Currencies |
| 7 | Importar transações e lançamentos | ETL ou API |
| 8 | Configurar conciliação bancária | Admin → ReconciliationConfig |
| 9 | Criar templates de demonstrações financeiras | Admin ou API |
| 10 | (Opcional) Configurar integração ERP | Admin → ERP Connections |

> **Dica:** Para grandes volumes de dados iniciais, use a [importação ETL](11-etl-importacao.md) que permite carregar planilhas Excel completas.

---

## 2.7 Erros Comuns

| Código | Significado | O que fazer |
|--------|-------------|-------------|
| `401 Unauthorized` | Token ausente ou inválido | Verifique se o header `Authorization: Token ...` está correto |
| `403 Forbidden` | Sem permissão | Verifique se o usuário tem acesso ao tenant/recurso |
| `404 Not Found` | Recurso não encontrado | Verifique o ID e o tenant na URL |
| `400 Bad Request` | Dados inválidos | Leia o corpo da resposta para ver os erros de validação |
| `500 Internal Server Error` | Erro no servidor | Contate o administrador do sistema |

### Exemplo de Erro de Validação

```json
{
  "date": ["Este campo é obrigatório."],
  "amount": ["Certifique-se de que este valor é maior que 0."]
}
```

---

*Anterior: [01 — Introdução](01-introducao.md) · Próximo: [03 — Painel Administrativo](03-admin-django.md)*

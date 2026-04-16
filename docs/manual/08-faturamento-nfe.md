# 08 — Faturamento e NF-e

O módulo de faturamento gerencia o ciclo completo de operações comerciais: cadastro de parceiros e produtos, contratos, faturas e o fluxo de notas fiscais eletrônicas (NF-e).

---

## 8.1 Parceiros Comerciais (Business Partners)

### Categorias de Parceiros

Os parceiros são organizados em **categorias hierárquicas** (MPTT):

```
Parceiros
├── Clientes
│   ├── Clientes Nacionais
│   └── Clientes Internacionais
├── Fornecedores
│   ├── Matéria-Prima
│   └── Serviços
└── Colaboradores
```

**Endpoints de Categorias:**

```bash
# Listar categorias
GET /acme/api/business_partner_categories/

# Criar categoria
POST /acme/api/business_partner_categories/
{"name": "Fornecedores de TI", "parent": 2}
```

### Cadastro de Parceiros

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `name` | string | Razão social ou nome |
| `category` | FK | Categoria hierárquica |
| `currency` | FK | Moeda padrão |
| `document` | string | CNPJ/CPF |
| `email`, `phone` | string | Contato |
| `address` | text | Endereço |

**Exemplo:**

```bash
POST /acme/api/business_partners/
{
  "name": "Fornecedor ABC Ltda",
  "category": 3,
  "currency": 1,
  "document": "12.345.678/0001-90",
  "email": "contato@abc.com.br"
}
```

**Endpoints:**

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/{tenant}/api/business_partners/` | Listar |
| `POST` | `/{tenant}/api/business_partners/` | Criar |
| `GET/PUT/PATCH/DELETE` | `/{tenant}/api/business_partners/{id}/` | CRUD |

---

## 8.2 Produtos e Serviços (Product Services)

### Categorias de Produtos

Assim como parceiros, produtos possuem **categorias hierárquicas**:

```
Produtos
├── Matéria-Prima
│   ├── Metais
│   └── Plásticos
├── Produto Acabado
│   ├── Linha A
│   └── Linha B
└── Serviços
    ├── Consultoria
    └── Manutenção
```

### Cadastro de Produtos

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `name` | string | Nome do produto/serviço |
| `code` | string | Código interno |
| `category` | FK | Categoria |
| `currency` | FK | Moeda |
| `unit_price` | decimal | Preço unitário |
| `ncm` | string | Código NCM (classificação fiscal) |

**Contas contábeis vinculadas (integração com estoque):**

| Campo | Descrição |
|-------|-----------|
| `inventory_account` | Conta de estoque |
| `cogs_account` | Conta de CMV (Custo dos Produtos Vendidos) |
| `revenue_account` | Conta de receita de venda |
| `inventory_adjustment_account` | Conta de ajuste de estoque |

**Exemplo:**

```bash
POST /acme/api/product_services/
{
  "name": "Parafuso M8x20",
  "code": "PAR-M8-20",
  "category": 5,
  "currency": 1,
  "unit_price": 0.45,
  "ncm": "7318.15.00"
}
```

---

## 8.3 Contratos (Contracts)

Contratos vinculam empresa, parceiro comercial e índice financeiro para reajuste.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `company` | FK | Empresa |
| `business_partner` | FK | Parceiro comercial |
| `financial_index` | FK | Índice de reajuste (IGPM, IPCA, etc.) |
| `start_date` / `end_date` | date | Vigência |
| `value` | decimal | Valor do contrato |

```bash
POST /acme/api/contracts/
{
  "business_partner": 5,
  "financial_index": 2,
  "start_date": "2026-01-01",
  "end_date": "2026-12-31",
  "value": 120000.00
}
```

> **Dica:** Vincule contratos a índices financeiros para cálculo automático de reajustes. Configure os índices em **Core → Financial Indices** no admin.

---

## 8.4 Faturas (Invoices)

### Criando uma Fatura

```bash
POST /acme/api/invoices/
{
  "business_partner": 5,
  "currency": 1,
  "issue_date": "2026-04-15",
  "due_date": "2026-05-15",
  "status": "draft"
}
```

### Adicionando Linhas

```bash
POST /acme/api/invoice_lines/
{
  "invoice": 1,
  "product_service": 10,
  "quantity": 100,
  "unit_price": 0.45,
  "total": 45.00
}
```

### Endpoints de Faturas

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/{tenant}/api/invoices/` | Listar |
| `POST` | `/{tenant}/api/invoices/` | Criar |
| `GET/PUT/PATCH/DELETE` | `/{tenant}/api/invoices/{id}/` | CRUD |
| `GET` | `/{tenant}/api/invoice_lines/` | Listar linhas |
| `POST` | `/{tenant}/api/invoice_lines/` | Criar linha |

---

## 8.5 Nota Fiscal Eletrônica (NF-e)

### Importação de NF-e

O principal fluxo para NF-e é a **importação** a partir de XML ou dados de integração:

```bash
POST /acme/api/nfe/import/
{
  "xml_content": "<nfeProc>...</nfeProc>"
}
```

Ou importação de múltiplas NF-e:

```bash
POST /acme/api/nfe/import/
{
  "notas": [
    {"chave_acesso": "35260412345678000190550010000001231234567890", ...},
    {"chave_acesso": "35260412345678000190550010000001241234567891", ...}
  ]
}
```

### Campos da NF-e

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `chave_acesso` | string(44) | Chave de acesso (44 dígitos) |
| `numero` | integer | Número da NF-e |
| `serie` | integer | Série |
| `emitente` | FK BusinessPartner | Emitente |
| `destinatario` | FK BusinessPartner | Destinatário |
| `data_emissao` | datetime | Data de emissão |
| `valor_total` | decimal | Valor total |
| `status` | choice | Status da NF-e |

### Itens da NF-e

Cada NF-e contém itens detalhados:

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `nota_fiscal` | FK NotaFiscal | NF-e pai |
| `product_service` | FK ProductService | Produto/serviço |
| `cfop` | FK CFOP | CFOP da operação |
| `quantidade` | decimal | Quantidade |
| `valor_unitario` | decimal | Valor unitário |
| `valor_total` | decimal | Valor total do item |

### Consultas e Análises

| Endpoint | Descrição |
|----------|-----------|
| `GET /{tenant}/api/nfe/` | Listar NF-e |
| `GET /{tenant}/api/nfe/{id}/` | Detalhe da NF-e |
| `GET /{tenant}/api/nfe/{id}/resumo/` | Resumo da NF-e |
| `GET /{tenant}/api/nfe/{id}/analises/` | Análises da NF-e |
| `GET /{tenant}/api/nfe/{id}/timeline/` | Timeline de eventos |
| `GET /{tenant}/api/nfe/canceladas/` | NF-e canceladas |
| `GET /{tenant}/api/nfe/com-cce/` | NF-e com carta de correção |
| `POST /{tenant}/api/nfe/{id}/manifestacao/` | Manifestação do destinatário |

### Eventos de NF-e

Eventos incluem cancelamentos, cartas de correção, manifestações, etc.

```bash
# Importar eventos
POST /acme/api/nfe/eventos/import/
{
  "eventos": [...]
}

# Listar eventos
GET /acme/api/nfe-eventos/
```

### CFOP (Código Fiscal de Operações e Prestações)

A tabela CFOP é pré-carregada no sistema:

```bash
# Listar CFOPs
GET /acme/api/cfop/

# Filtrar por tipo de operação
GET /acme/api/cfop/?tipo_operacao=entrada
```

---

## 8.6 Fluxo Completo — Exemplo Prático

### Cenário: Receber NF-e de fornecedor e lançar na contabilidade

**1. Importar a NF-e:**
```bash
POST /acme/api/nfe/import/
{"xml_content": "<nfeProc>...XML da NF-e...</nfeProc>"}
```

**2. Verificar a importação:**
```bash
GET /acme/api/nfe/?chave_acesso=35260412345678...
```

**3. Analisar a NF-e:**
```bash
GET /acme/api/nfe/{id}/analises/
```

**4. Gerar movimentação de estoque (se aplicável):**
```bash
POST /acme/api/inventory/movements/ingest_nf/
{"nota_fiscal_id": 1}
```

**5. Criar transação contábil:**
```bash
POST /acme/api/transactions/
{
  "entity": 1,
  "date": "2026-04-15",
  "amount": 15000.00,
  "currency": 1,
  "description": "NF-e 1234 - Fornecedor ABC"
}
```

---

## 8.7 Dicas Avançadas

### Importação em Lote de NF-e

Para grandes volumes de notas fiscais, use o pipeline ETL ou a importação em lote pela API. O sistema detecta duplicatas pela chave de acesso.

### Timeline de NF-e por Chave

```bash
GET /acme/api/nfe/{id}/timeline-por-chave/
```

Retorna todos os eventos relacionados a uma NF-e organizados cronologicamente.

### Integração com Estoque

Quando produtos têm contas contábeis vinculadas (`inventory_account`, `cogs_account`), a importação de NF-e pode automaticamente:
1. Criar movimentações de estoque
2. Gerar camadas de custeio
3. Produzir impactos contábeis

Veja [10 — Estoque](10-estoque.md) para detalhes.

---

*Anterior: [07 — Demonstrações Financeiras](07-demonstracoes-financeiras.md) · Próximo: [09 — Recursos Humanos](09-rh-folha.md)*

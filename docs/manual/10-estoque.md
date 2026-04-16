# 10 — Estoque

O módulo de estoque gerencia almoxarifados, movimentações, camadas de custeio, valoração e alertas de inventário. Ele se integra profundamente com o faturamento (NF-e) e a contabilidade.

---

## 10.1 Almoxarifados (Warehouses)

Almoxarifados representam os locais físicos de armazenamento.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `name` | string | Nome do almoxarifado |
| `code` | string | Código interno |
| `address` | text | Endereço |
| `is_active` | boolean | Ativo |

```bash
# Criar almoxarifado
POST /acme/api/inventory/warehouses/
{
  "name": "Depósito Central",
  "code": "DEP-01",
  "address": "Rua Principal, 100 - São Paulo"
}
```

---

## 10.2 Unidades de Medida

### Unidades Básicas (UoM)

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `name` | string | Nome (ex: quilograma, unidade, caixa) |
| `abbreviation` | string | Abreviação (kg, un, cx) |

```bash
POST /acme/api/inventory/uom/
{"name": "Quilograma", "abbreviation": "kg"}
```

### Conversões entre Unidades (UoM Conversions)

Defina como converter entre unidades de medida:

```bash
POST /acme/api/inventory/uom-conversions/
{
  "from_uom": 1,
  "to_uom": 2,
  "factor": 1000,
  "product_service": 5
}
```

> **Nota:** Conversões podem ser globais (sem `product_service`) ou específicas por produto.

---

## 10.3 Movimentações de Estoque (Stock Movements)

Movimentações são **imutáveis** — uma vez criadas, não podem ser editadas ou excluídas. Para corrigir erros, crie uma movimentação inversa.

### Campos

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `product_service` | FK ProductService | Produto |
| `warehouse` | FK Warehouse | Almoxarifado (opcional) |
| `uom` | FK UoM | Unidade de medida |
| `quantity` | decimal | Quantidade (+ entrada, - saída) |
| `unit_cost` | decimal | Custo unitário |
| `movement_type` | choice | Tipo de movimentação |
| `date` | datetime | Data da movimentação |
| `nota_fiscal` | FK NotaFiscal | NF-e vinculada (opcional) |
| `nota_fiscal_item` | FK NotaFiscalItem | Item da NF-e (opcional) |

### Tipos de Movimentação

| Tipo | Descrição |
|------|-----------|
| `purchase` | Compra/entrada |
| `sale` | Venda/saída |
| `adjustment_in` | Ajuste de entrada |
| `adjustment_out` | Ajuste de saída |
| `transfer` | Transferência entre almoxarifados |
| `return` | Devolução |
| `production` | Entrada por produção |
| `consumption` | Saída por consumo |

### Criação Manual

```bash
POST /acme/api/inventory/movements/manual/
{
  "product_service": 5,
  "warehouse": 1,
  "uom": 1,
  "quantity": 100,
  "unit_cost": 12.50,
  "movement_type": "purchase",
  "date": "2026-04-15T10:00:00Z"
}
```

### Ingestão a partir de NF-e

Converte automaticamente itens de uma NF-e em movimentações de estoque:

```bash
POST /acme/api/inventory/movements/ingest_nf/
{"nota_fiscal_id": 42}
```

### Ingestão de Pendentes

Processa NF-e importadas que ainda não geraram movimentações:

```bash
POST /acme/api/inventory/movements/ingest_pending/
```

---

## 10.4 Saldos de Estoque (Inventory Balances)

Saldos são calculados automaticamente a partir das movimentações.

```bash
# Listar saldos
GET /acme/api/inventory/balances/

# Filtrar por produto
GET /acme/api/inventory/balances/?product_service=5

# Filtrar por almoxarifado
GET /acme/api/inventory/balances/?warehouse=1
```

**Campos do saldo:**

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `product_service` | FK | Produto |
| `warehouse` | FK | Almoxarifado (opcional) |
| `quantity` | decimal | Quantidade em estoque |
| `average_cost` | decimal | Custo médio |
| `total_value` | decimal | Valor total em estoque |

---

## 10.5 Camadas de Custeio (Inventory Layers)

O sistema mantém camadas de custeio para apuração correta do custo dos produtos.

### Métodos de Custeio

A configuração de custeio é feita por empresa:

```bash
# Verificar configuração
GET /acme/api/inventory/costing/
```

| Método | Descrição |
|--------|-----------|
| **FIFO** | First In, First Out — primeiro que entra, primeiro que sai |
| **Custo Médio** | Média ponderada das entradas |

### Computar Custeio

```bash
POST /acme/api/inventory/costing/compute/
{
  "product_service": 5,
  "date_from": "2026-01-01",
  "date_to": "2026-03-31"
}
```

---

## 10.6 Alertas de Estoque (Inventory Alerts)

O sistema gera alertas automáticos para situações que requerem atenção.

| Tipo de Alerta | Descrição |
|----------------|-----------|
| Estoque mínimo | Quantidade abaixo do mínimo definido |
| Divergência | Diferença entre saldo contábil e físico |
| Sem movimento | Produto sem movimentação por período prolongado |
| NF-e sem movimento | Nota fiscal sem movimentação de estoque gerada |

```bash
# Listar alertas
GET /acme/api/inventory/alerts/

# Marcar alerta como resolvido
PATCH /acme/api/inventory/alerts/{id}/
{"resolved": true}
```

---

## 10.7 Relatórios Comparativos

### Relatório de Comparação

Compara estoque contábil vs estoque físico:

```bash
GET /acme/api/inventory/comparison/report/
```

### Por SKU

```bash
GET /acme/api/inventory/comparison/sku/?product_service=5
```

### Por Movimentação

```bash
GET /acme/api/inventory/comparison/movement/?date_from=2026-01-01&date_to=2026-03-31
```

---

## 10.8 Configuração de Custeio por Empresa

A `TenantCostingConfig` define como o estoque é custeado e quais contas contábeis são usadas:

| Campo | Descrição |
|-------|-----------|
| `costing_method` | Método de custeio (FIFO ou média) |
| `inventory_account` | Conta contábil de estoque |
| `cogs_account` | Conta de CMV |
| `adjustment_account` | Conta de ajustes |
| `valuation_account` | Conta de valoração |

> **Dica:** Configure as contas contábeis no `TenantCostingConfig` para que os impactos contábeis de movimentações de estoque sejam gerados automaticamente.

---

## 10.9 Impactos Contábeis

Quando configurado, movimentações de estoque geram automaticamente:

1. **Entrada (compra):** Débito em Estoque, Crédito em Fornecedores
2. **Saída (venda):** Débito em CMV, Crédito em Estoque
3. **Ajustes:** Débito/Crédito conforme conta de ajuste

```bash
# Verificar impactos contábeis gerados
GET /acme/api/inventory/accounting-impacts/
```

---

## 10.10 Fluxo Completo — Entrada de Mercadoria via NF-e

**1. Importar NF-e do fornecedor:**
```bash
POST /acme/api/nfe/import/
{"xml_content": "..."}
```

**2. Gerar movimentações de estoque:**
```bash
POST /acme/api/inventory/movements/ingest_nf/
{"nota_fiscal_id": 42}
```

**3. Verificar saldos atualizados:**
```bash
GET /acme/api/inventory/balances/?product_service=5
```

**4. Verificar impactos contábeis:**
```bash
GET /acme/api/inventory/accounting-impacts/?nota_fiscal=42
```

**5. Verificar alertas:**
```bash
GET /acme/api/inventory/alerts/?product_service=5
```

---

## 10.11 Dicas Avançadas

- **Movimentações imutáveis:** Nunca tente editar uma movimentação. Para corrigir, crie um ajuste inverso
- **Custeio periódico:** Execute o cálculo de custeio mensalmente para manter a valoração atualizada
- **Integração NF-e → Estoque:** Configure os produtos com contas contábeis vinculadas para fluxo automático
- **Alertas proativos:** Configure níveis mínimos de estoque no cadastro de produtos

---

*Anterior: [09 — RH e Folha](09-rh-folha.md) · Próximo: [11 — Importação ETL](11-etl-importacao.md)*

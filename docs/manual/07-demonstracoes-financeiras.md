# 07 — Demonstrações Financeiras

O módulo de demonstrações financeiras permite gerar, personalizar e exportar relatórios contábeis como DRE (Demonstração do Resultado do Exercício), Balanço Patrimonial e Fluxo de Caixa.

---

## 7.1 Conceitos

### Templates e Demonstrações

O sistema separa dois conceitos:

- **Template** — Define a *estrutura* de um demonstrativo (quais linhas, quais contas, quais fórmulas)
- **Demonstração** — Uma *instância* gerada a partir de um template para um período específico, com valores calculados

```
Template (estrutura)          Demonstração (resultado)
├─ Receita Bruta              ├─ Receita Bruta: R$ 500.000
│  └─ contas: 4.1.*           │  └─ contas: R$ 500.000
├─ (-) Deduções               ├─ (-) Deduções: R$ -50.000
│  └─ contas: 4.2.*           │  └─ contas: R$ -50.000
├─ = Receita Líquida          ├─ = Receita Líquida: R$ 450.000
│  └─ fórmula: L1 - L2        │  └─ calculado
```

### Fórmulas de Linha

As linhas de template podem usar fórmulas para referenciar outras linhas:

| Sintaxe | Significado | Exemplo |
|---------|-------------|---------|
| `L1` | Valor da linha 1 | `L1 + L2` |
| `L3 - L4` | Subtração | `L3 - L4` |
| `L1 + L2 + L3` | Soma múltipla | Receita total |
| `L5 / L1 * 100` | Percentual | Margem operacional |

> **Atenção:** Fórmulas são avaliadas **na ordem das linhas**. Uma linha só pode referenciar linhas anteriores.

---

## 7.2 Gerenciando Templates

### Criar Template

```bash
POST /acme/api/financial-statement-templates/
{
  "name": "DRE Padrão",
  "type": "income_statement",
  "company": 1,
  "currency": 1
}
```

**Tipos de template:**

| Tipo | Descrição |
|------|-----------|
| `income_statement` | Demonstração do Resultado (DRE) |
| `balance_sheet` | Balanço Patrimonial |
| `cash_flow` | Fluxo de Caixa |

### Criar Linhas do Template

```bash
POST /acme/api/financial-statement-templates/{id}/lines/
{
  "lines": [
    {"order": 1, "label": "Receita Bruta", "account_filter": "4.1", "sign": 1},
    {"order": 2, "label": "(-) Deduções da Receita", "account_filter": "4.2", "sign": -1},
    {"order": 3, "label": "= Receita Líquida", "formula": "L1 + L2"},
    {"order": 4, "label": "(-) Custo dos Produtos Vendidos", "account_filter": "5.1", "sign": -1},
    {"order": 5, "label": "= Lucro Bruto", "formula": "L3 + L4"},
    {"order": 6, "label": "(-) Despesas Operacionais", "account_filter": "5.2,5.3,5.4", "sign": -1},
    {"order": 7, "label": "= Lucro Operacional", "formula": "L5 + L6"},
    {"order": 8, "label": "Margem Operacional (%)", "formula": "L7 / L3 * 100"}
  ]
}
```

### Duplicar Template

```bash
POST /acme/api/financial-statement-templates/{id}/duplicate/
```

Cria uma cópia do template com todas as suas linhas.

### Definir Template Padrão

```bash
POST /acme/api/financial-statement-templates/{id}/set_default/
```

### Sugestão de Templates

O sistema pode sugerir templates baseados no plano de contas:

```bash
GET /acme/api/financial-statement-templates/suggest_templates/
```

---

## 7.3 Gerando Demonstrações

### Gerar Demonstração

```bash
POST /acme/api/financial-statements/generate/
{
  "template": 1,
  "start_date": "2026-01-01",
  "end_date": "2026-03-31",
  "entity": 1,
  "currency": 1
}
```

A geração calcula os valores de cada linha do template para o período informado.

### Preview (sem salvar)

```bash
POST /acme/api/financial-statements/preview/
{
  "template": 1,
  "start_date": "2026-01-01",
  "end_date": "2026-03-31"
}
```

Retorna os valores calculados sem persistir o demonstrativo.

---

## 7.4 Demonstrações Rápidas (Quick Statements)

Para gerar demonstrativos sem precisar criar um template primeiro:

### DRE Rápida

```bash
POST /acme/api/financial-statements/quick_income_statement/
{
  "start_date": "2026-01-01",
  "end_date": "2026-03-31",
  "entity": 1
}
```

### Balanço Patrimonial Rápido

```bash
POST /acme/api/financial-statements/quick_balance_sheet/
{
  "reference_date": "2026-03-31",
  "entity": 1
}
```

---

## 7.5 DRE Detalhada

Para uma DRE com abertura por conta e subconta:

```bash
POST /acme/api/financial-statements/detailed_income_statement/
{
  "start_date": "2026-01-01",
  "end_date": "2026-03-31",
  "entity": 1,
  "parent_accounts": [4, 5],
  "balance_type": "movement"
}
```

**Parâmetros:**

| Parâmetro | Descrição |
|-----------|-----------|
| `parent_accounts` | IDs das contas-pai a detalhar (ex: Receitas e Despesas) |
| `balance_type` | `movement` (movimentação do período) ou `balance` (saldo acumulado) |
| `include_zero` | Incluir contas com movimento zero (padrão: `false`) |

### Balanço Detalhado

```bash
POST /acme/api/financial-statements/detailed_balance_sheet/
{
  "reference_date": "2026-03-31",
  "entity": 1
}
```

### Fluxo de Caixa Detalhado

```bash
POST /acme/api/financial-statements/detailed_cash_flow/
{
  "start_date": "2026-01-01",
  "end_date": "2026-03-31",
  "entity": 1
}
```

---

## 7.6 Comparações entre Períodos

### Criar Comparação

```bash
POST /acme/api/financial-statement-comparisons/
{
  "statement_a": 1,
  "statement_b": 2,
  "name": "Q1 2026 vs Q1 2025"
}
```

### Obter Dados da Comparação

```bash
GET /acme/api/financial-statement-comparisons/{id}/comparison_data/
```

Retorna variação absoluta e percentual linha a linha.

---

## 7.7 Série Temporal

Para análise de tendência ao longo do tempo:

```bash
GET /acme/api/financial-statements/time_series/?template=1&periods=12&interval=monthly
```

Retorna os valores de cada linha do template para cada período, permitindo construir gráficos de evolução.

---

## 7.8 Exportação

### Exportar como PDF

```bash
GET /acme/api/financial-statements/{id}/export_pdf/
```

### Exportar como Excel

```bash
GET /acme/api/financial-statements/{id}/export_excel/
```

### Exportar como HTML

```bash
GET /acme/api/financial-statements/{id}/export_html/
```

### Exportar como Markdown

```bash
GET /acme/api/financial-statements/{id}/export_markdown/
```

---

## 7.9 Ciclo de Vida do Demonstrativo

| Ação | Método | Endpoint |
|------|--------|----------|
| **Gerar** | POST | `/financial-statements/generate/` |
| **Finalizar** | POST | `/financial-statements/{id}/finalize/` |
| **Arquivar** | POST | `/financial-statements/{id}/archive/` |

**Finalizar** impede alterações. **Arquivar** move para histórico.

---

## 7.10 Preview de Templates

Para testar um template antes de gerar o demonstrativo oficial:

**Via API:**
```bash
POST /acme/financial-statements/template-preview/
{
  "template_id": 1,
  "start_date": "2026-01-01",
  "end_date": "2026-03-31"
}
```

**Via Management Command (admin do sistema):**
```bash
python manage.py test_financial_statements --template 1 --start 2026-01-01 --end 2026-03-31 --preview
```

Use `--debug-accounts` para ver o detalhamento de quais contas contribuem para cada linha.

---

## 7.11 Exemplo Prático — DRE Mensal

### 1. Criar Template de DRE

```bash
POST /acme/api/financial-statement-templates/
{"name": "DRE Mensal", "type": "income_statement", "currency": 1}
```

### 2. Definir Linhas

```bash
# Linhas simplificadas
L1: Receita Operacional → contas 4.*
L2: (-) Deduções → contas 4.9.*
L3: = Receita Líquida → fórmula: L1 + L2
L4: (-) CMV → contas 5.1.*
L5: = Lucro Bruto → fórmula: L3 + L4
L6: (-) Despesas Administrativas → contas 5.2.*
L7: (-) Despesas Comerciais → contas 5.3.*
L8: = Resultado Operacional → fórmula: L5 + L6 + L7
```

### 3. Gerar para Março/2026

```bash
POST /acme/api/financial-statements/generate/
{
  "template": 1,
  "start_date": "2026-03-01",
  "end_date": "2026-03-31"
}
```

### 4. Exportar PDF

```bash
GET /acme/api/financial-statements/{id}/export_pdf/
```

---

## 7.12 Dicas Avançadas

### Fórmulas

- Mantenha fórmulas simples: `L1 + L2`, `L3 - L4`
- Para percentuais: `L5 / L3 * 100`
- Linhas referenciadas **devem ter order menor** que a linha que as referencia
- Evite referências circulares

### Performance

- Use o `AccountBalanceHistory` para cálculos rápidos (recalcule periodicamente)
- Para períodos muito longos, gere demonstrativos menores e use comparações

### Boas Práticas

- Crie templates separados para DRE gerencial e DRE contábil
- Mantenha versões dos templates (duplique antes de alterar)
- Finalize demonstrativos após revisão para evitar alterações acidentais
- Use comparações para análise de variação mês a mês ou ano a ano

---

*Anterior: [06 — Conciliação Bancária](06-conciliacao-bancaria.md) · Próximo: [08 — Faturamento e NF-e](08-faturamento-nfe.md)*

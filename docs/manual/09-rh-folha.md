# 09 — Recursos Humanos e Folha de Pagamento

O módulo de RH gerencia a estrutura organizacional de pessoas: cargos, funcionários, controle de ponto, indicadores de desempenho, bonificações e folha de pagamento.

---

## 9.1 Cargos (Positions)

Cargos definem a estrutura de posições da empresa, incluindo faixa salarial.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `name` | string | Nome do cargo |
| `min_salary` | decimal | Salário mínimo da faixa |
| `max_salary` | decimal | Salário máximo da faixa |
| `description` | text | Descrição das responsabilidades |

### Endpoints

```bash
# Listar cargos
GET /acme/api/positions/

# Criar cargo
POST /acme/api/positions/
{
  "name": "Analista Financeiro Sênior",
  "min_salary": 8000.00,
  "max_salary": 12000.00,
  "description": "Responsável por análises financeiras e conciliações"
}
```

---

## 9.2 Funcionários (Employees)

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `name` | string | Nome completo |
| `position` | FK Position | Cargo |
| `hire_date` | date | Data de admissão |
| `salary` | decimal | Salário atual |
| `document` | string | CPF |
| `email` | string | Email corporativo |
| `is_active` | boolean | Funcionário ativo |

### Endpoints

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/{tenant}/api/employees/` | Listar funcionários |
| `POST` | `/{tenant}/api/employees/` | Cadastrar funcionário |
| `GET/PUT/PATCH` | `/{tenant}/api/employees/{id}/` | Consultar/atualizar |
| `DELETE` | `/{tenant}/api/employees/{id}/` | Desativar |

### Exemplo

```bash
POST /acme/api/employees/
{
  "name": "Maria Silva",
  "position": 3,
  "hire_date": "2024-03-15",
  "salary": 9500.00,
  "document": "123.456.789-00",
  "email": "maria.silva@empresa.com"
}
```

---

## 9.3 Controle de Ponto (Time Tracking)

Registro de horas trabalhadas por funcionário, agregadas mensalmente.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `employee` | FK Employee | Funcionário |
| `month` | date | Mês de referência |
| `hours_worked` | decimal | Horas trabalhadas |
| `overtime_hours` | decimal | Horas extras |
| `absences` | integer | Faltas |
| `late_arrivals` | integer | Atrasos |

```bash
POST /acme/api/timetracking/
{
  "employee": 1,
  "month": "2026-04-01",
  "hours_worked": 176,
  "overtime_hours": 12,
  "absences": 0,
  "late_arrivals": 2
}
```

---

## 9.4 Indicadores de Desempenho (KPIs)

Acompanhe métricas de performance por funcionário.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `employee` | FK Employee | Funcionário |
| `name` | string | Nome do indicador |
| `target_value` | decimal | Meta |
| `actual_value` | decimal | Valor realizado |
| `period` | date | Período de referência |

```bash
POST /acme/api/kpis/
{
  "employee": 1,
  "name": "Taxa de Conciliação",
  "target_value": 95.0,
  "actual_value": 92.5,
  "period": "2026-03-01"
}
```

---

## 9.5 Bonificações (Bonuses)

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `employee` | FK Employee | Funcionário |
| `amount` | decimal | Valor do bônus |
| `reason` | text | Justificativa |
| `date` | date | Data de concessão |

```bash
POST /acme/api/bonuses/
{
  "employee": 1,
  "amount": 2000.00,
  "reason": "Meta de conciliação superada em 5%",
  "date": "2026-04-10"
}
```

---

## 9.6 Ajustes Recorrentes (Recurring Adjustments)

Ajustes aplicados automaticamente na folha de pagamento todo mês.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `employee` | FK Employee | Funcionário |
| `name` | string | Descrição do ajuste |
| `amount` | decimal | Valor (positivo = provento, negativo = desconto) |
| `accounts` | M2M Account | Contas contábeis vinculadas |
| `start_date` / `end_date` | date | Vigência |

**Exemplos de uso:**
- Vale-transporte (desconto recorrente)
- Plano de saúde (desconto recorrente)
- Adicional de periculosidade (provento recorrente)
- Pensão alimentícia (desconto judicial)

```bash
POST /acme/api/recurring-adjustments/
{
  "employee": 1,
  "name": "Vale-Transporte",
  "amount": -350.00,
  "start_date": "2026-01-01",
  "accounts": [45]
}
```

---

## 9.7 Folha de Pagamento (Payroll)

### Estrutura

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `employee` | FK Employee | Funcionário |
| `company` | FK Company | Empresa |
| `month` | date | Mês de referência |
| `gross_salary` | decimal | Salário bruto |
| `deductions` | decimal | Total de descontos |
| `net_salary` | decimal | Salário líquido |
| `status` | choice | Status (rascunho/calculado/pago) |

### Geração Mensal em Lote

```bash
POST /acme/api/payrolls/generate-monthly/
{
  "month": "2026-04",
  "employee_ids": [1, 2, 3, 5, 8]
}
```

Gera a folha de pagamento para todos os funcionários especificados, aplicando automaticamente:
- Salário base do funcionário
- Ajustes recorrentes ativos no período
- Bônus aprovados para o mês
- Dados de ponto (horas extras, faltas)

### Recalcular Folha

```bash
POST /acme/api/payrolls/{id}/recalculate/
```

Útil quando dados de ponto, bônus ou ajustes são alterados após a geração.

### Atualização em Lote de Status

```bash
POST /acme/api/payrolls/bulk-update-status/
{
  "payroll_ids": [1, 2, 3],
  "status": "paid"
}
```

### Endpoints de Folha

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/{tenant}/api/payrolls/` | Listar folhas |
| `POST` | `/{tenant}/api/payrolls/` | Criar folha individual |
| `POST` | `/{tenant}/api/payrolls/generate-monthly/` | Gerar folhas em lote |
| `POST` | `/{tenant}/api/payrolls/{id}/recalculate/` | Recalcular |
| `POST` | `/{tenant}/api/payrolls/bulk-update-status/` | Atualizar status em lote |

---

## 9.8 Fluxo Completo — Processamento de Folha Mensal

### Passo a Passo

**1. Verificar dados de ponto:**
```bash
GET /acme/api/timetracking/?month=2026-04-01
```

**2. Revisar ajustes recorrentes ativos:**
```bash
GET /acme/api/recurring-adjustments/?is_active=true
```

**3. Verificar bônus aprovados:**
```bash
GET /acme/api/bonuses/?date_after=2026-04-01&date_before=2026-04-30
```

**4. Gerar folha do mês:**
```bash
POST /acme/api/payrolls/generate-monthly/
{"month": "2026-04"}
```

**5. Revisar e ajustar se necessário:**
```bash
GET /acme/api/payrolls/?month=2026-04-01
```

**6. Recalcular se houve alterações:**
```bash
POST /acme/api/payrolls/{id}/recalculate/
```

**7. Marcar como pago:**
```bash
POST /acme/api/payrolls/bulk-update-status/
{"payroll_ids": [1, 2, 3], "status": "paid"}
```

---

## 9.9 Dicas

- **Fluxo mensal:** Feche o ponto → Registre bônus → Gere a folha → Revise → Pague
- **Ajustes recorrentes:** Cadastre uma vez, aplica-se automaticamente todo mês
- **Vinculação contábil:** Vincule ajustes recorrentes a contas contábeis para lançamento automático na contabilidade
- **Histórico:** Consulte folhas anteriores filtrando por mês para análises comparativas

---

*Anterior: [08 — Faturamento e NF-e](08-faturamento-nfe.md) · Próximo: [10 — Estoque](10-estoque.md)*

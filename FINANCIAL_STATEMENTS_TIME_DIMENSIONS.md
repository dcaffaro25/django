# Financial Statements - Time Dimensions and Comparisons

## Visão Geral

Este documento descreve as funcionalidades de dimensões temporais e comparações implementadas para os relatórios financeiros.

## Funcionalidades

### 1. Séries Temporais (Time Series)

Permite gerar séries temporais agrupadas por diferentes dimensões de tempo para análise de tendências, especialmente útil para Cash Flow.

**Dimensões Disponíveis:**
- `day`: Agrupa por dia
- `week`: Agrupa por semana (segunda a domingo)
- `month`: Agrupa por mês
- `quarter`: Agrupa por trimestre
- `semester`: Agrupa por semestre
- `year`: Agrupa por ano

### 2. Comparações de Períodos

Permite comparar o período atual com outros períodos, útil para Income Statement e Balance Sheet.

**Tipos de Comparação:**
- `previous_period`: Período anterior de mesmo tamanho
- `previous_year`: Mesmo período do ano anterior
- `ytd_previous_year`: Year-to-date do ano anterior
- `last_12_months`: Últimos 12 meses (rolling)
- `same_period_last_year`: Mesmas datas do ano anterior

## Endpoints

### 1. Time Series

**Endpoint:** `POST /api/financial-statements/time_series/`

**Request:**
```json
{
  "template_id": 1,
  "start_date": "2025-01-01",
  "end_date": "2025-12-31",
  "dimension": "month",
  "line_numbers": [1, 2, 3],  // opcional
  "include_pending": false
}
```

**Response:**
```json
{
  "template_id": 1,
  "template_name": "Cash Flow Statement",
  "report_type": "cash_flow",
  "dimension": "month",
  "start_date": "2025-01-01",
  "end_date": "2025-12-31",
  "lines": [
    {
      "line_number": 1,
      "label": "Operating Cash Flow",
      "line_type": "account",
      "data": [
        {
          "period_key": "2025-01",
          "period_label": "January 2025",
          "start_date": "2025-01-01",
          "end_date": "2025-01-31",
          "value": 50000.00
        },
        {
          "period_key": "2025-02",
          "period_label": "February 2025",
          "start_date": "2025-02-01",
          "end_date": "2025-02-28",
          "value": 45000.00
        }
        // ... mais períodos
      ]
    }
    // ... mais linhas
  ]
}
```

**Exemplo de Uso - Cash Flow Mensal:**
```python
import requests

response = requests.post(
    'https://api.example.com/api/financial-statements/time_series/',
    json={
        'template_id': 1,  # Cash Flow template
        'start_date': '2025-01-01',
        'end_date': '2025-12-31',
        'dimension': 'month',
        'include_pending': False
    },
    headers={'Authorization': 'Token YOUR_TOKEN'}
)

data = response.json()
# data['lines'] contém séries temporais para cada linha do template
```

### 2. Comparações

**Endpoint:** `POST /api/financial-statements/with_comparisons/`

**Request:**
```json
{
  "template_id": 1,
  "start_date": "2025-01-01",
  "end_date": "2025-03-31",
  "comparison_types": ["previous_period", "previous_year"],
  "include_pending": false
}
```

**Response:**
```json
{
  "statement": {
    "id": 123,
    "name": "Income Statement Q1 2025",
    "start_date": "2025-01-01",
    "end_date": "2025-03-31",
    "lines": [
      {
        "line_number": 1,
        "label": "Revenue",
        "balance": 100000.00
      },
      {
        "line_number": 2,
        "label": "Expenses",
        "balance": 75000.00
      }
      // ... mais linhas
    ]
  },
  "comparisons": {
    "previous_period": {
      "start_date": "2024-10-01",
      "end_date": "2024-12-31",
      "lines": {
        "1": {
          "current_value": 100000.00,
          "comparison_value": 95000.00,
          "absolute_change": 5000.00,
          "percentage_change": 5.26,
          "comparison_type": "previous_period"
        },
        "2": {
          "current_value": 75000.00,
          "comparison_value": 70000.00,
          "absolute_change": 5000.00,
          "percentage_change": 7.14,
          "comparison_type": "previous_period"
        }
        // ... mais linhas
      }
    },
    "previous_year": {
      "start_date": "2024-01-01",
      "end_date": "2024-03-31",
      "lines": {
        "1": {
          "current_value": 100000.00,
          "comparison_value": 90000.00,
          "absolute_change": 10000.00,
          "percentage_change": 11.11,
          "comparison_type": "previous_year"
        }
        // ... mais linhas
      }
    }
  }
}
```

**Exemplo de Uso - Income Statement com Comparações:**
```python
import requests

response = requests.post(
    'https://api.example.com/api/financial-statements/with_comparisons/',
    json={
        'template_id': 2,  # Income Statement template
        'start_date': '2025-01-01',
        'end_date': '2025-03-31',
        'comparison_types': ['previous_period', 'previous_year', 'ytd_previous_year'],
        'include_pending': False
    },
    headers={'Authorization': 'Token YOUR_TOKEN'}
)

data = response.json()
statement = data['statement']
comparisons = data['comparisons']

# Acessar comparação específica
prev_year = comparisons['previous_year']
for line_num, comp_data in prev_year['lines'].items():
    print(f"Line {line_num}: {comp_data['percentage_change']}% change")
```

## Casos de Uso

### Cash Flow - Análise Mensal

Para visualizar o fluxo de caixa ao longo do tempo:

```json
POST /api/financial-statements/time_series/
{
  "template_id": 1,
  "start_date": "2025-01-01",
  "end_date": "2025-12-31",
  "dimension": "month"
}
```

Isso retorna uma série temporal mensal que pode ser usada para:
- Gráficos de linha mostrando tendências
- Identificar sazonalidade
- Análise de padrões de fluxo de caixa

### Income Statement - Comparação Trimestral

Para comparar trimestres:

```json
POST /api/financial-statements/with_comparisons/
{
  "template_id": 2,
  "start_date": "2025-01-01",
  "end_date": "2025-03-31",
  "comparison_types": ["previous_period", "previous_year"]
}
```

Isso permite:
- Ver crescimento trimestre a trimestre
- Comparar com mesmo período do ano anterior
- Calcular variações percentuais

### Balance Sheet - Comparação Anual

Para comparar balanços em diferentes pontos no tempo:

```json
POST /api/financial-statements/with_comparisons/
{
  "template_id": 3,
  "start_date": "2025-12-31",
  "end_date": "2025-12-31",
  "comparison_types": ["previous_year"]
}
```

## Utilitários

### Funções de Dimensões Temporais

O módulo `accounting.utils_time_dimensions` fornece:

- `get_period_start(date, dimension)`: Início do período
- `get_period_end(date, dimension)`: Fim do período
- `get_period_key(date, dimension)`: Chave única do período
- `generate_periods(start_date, end_date, dimension)`: Lista de períodos
- `format_period_label(date, dimension)`: Label formatado

### Funções de Comparação

- `get_comparison_period(current_start, current_end, comparison_type)`: Obtém período de comparação
- `calculate_period_comparison(current_value, comparison_value, comparison_type)`: Calcula métricas de comparação

## Performance

**Notas:**
- Séries temporais podem gerar muitos períodos (especialmente com `dimension='day'`)
- Considere limitar o range de datas ou usar `line_numbers` para linhas específicas
- Comparações geram statements adicionais, o que pode ser custoso
- Use `include_pending=False` para melhor performance (apenas posted entries)

## Exemplos Avançados

### Cash Flow Semanal

```python
# Análise de fluxo de caixa semanal para últimos 3 meses
from datetime import date, timedelta

end_date = date.today()
start_date = end_date - timedelta(days=90)

response = requests.post(
    '/api/financial-statements/time_series/',
    json={
        'template_id': 1,
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
        'dimension': 'week',
        'line_numbers': [1, 2, 3]  # Apenas linhas específicas
    }
)
```

### Income Statement com Múltiplas Comparações

```python
# Comparar Q1 2025 com Q4 2024, Q1 2024, e YTD 2024
response = requests.post(
    '/api/financial-statements/with_comparisons/',
    json={
        'template_id': 2,
        'start_date': '2025-01-01',
        'end_date': '2025-03-31',
        'comparison_types': [
            'previous_period',      # Q4 2024
            'previous_year',        # Q1 2024
            'ytd_previous_year'     # YTD até março 2024
        ]
    }
)
```

## Integração com Frontend

### Visualização de Séries Temporais

```javascript
// Exemplo usando Chart.js
const response = await fetch('/api/financial-statements/time_series/', {
  method: 'POST',
  body: JSON.stringify({
    template_id: 1,
    start_date: '2025-01-01',
    end_date: '2025-12-31',
    dimension: 'month'
  })
});

const data = await response.json();

// Preparar dados para gráfico
const labels = data.lines[0].data.map(d => d.period_label);
const values = data.lines[0].data.map(d => d.value);

new Chart(ctx, {
  type: 'line',
  data: {
    labels: labels,
    datasets: [{
      label: data.lines[0].label,
      data: values
    }]
  }
});
```

### Tabela de Comparações

```javascript
// Exemplo de tabela HTML
const response = await fetch('/api/financial-statements/with_comparisons/', {
  method: 'POST',
  body: JSON.stringify({
    template_id: 2,
    start_date: '2025-01-01',
    end_date: '2025-03-31',
    comparison_types: ['previous_year']
  })
});

const data = await response.json();
const comparison = data.comparisons.previous_year;

// Criar tabela
data.statement.lines.forEach(line => {
  const comp = comparison.lines[line.line_number];
  console.log(`
    ${line.label}:
    Current: ${line.balance}
    Previous: ${comp.comparison_value}
    Change: ${comp.absolute_change} (${comp.percentage_change}%)
  `);
});
```

## Migração

Se você já estava usando os endpoints básicos de geração de statements, esses novos endpoints são adicionais e não quebram funcionalidade existente.

Para migrar para usar séries temporais ou comparações, simplesmente use os novos endpoints em vez de gerar múltiplos statements manualmente.


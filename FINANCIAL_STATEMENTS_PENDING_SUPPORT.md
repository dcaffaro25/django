# Financial Statements - Suporte para Pending e Revisão de Status

## Mudanças Implementadas

### 1. Suporte para Incluir Pending nos Relatórios

#### Parâmetro `include_pending`
Adicionado suporte para incluir transações e journal entries pendentes nos relatórios financeiros.

**Como usar:**
```json
POST /api/financial-statements/generate/
{
  "template_id": 1,
  "start_date": "2025-01-01",
  "end_date": "2025-12-31",
  "include_pending": true  // Novo parâmetro
}
```

**Comportamento:**
- `include_pending: false` (padrão): Apenas journal entries com `state='posted'` são incluídos
- `include_pending: true`: Journal entries com `state='posted'` ou `state='pending'` são incluídos

**Onde é aplicado:**
- **Balance Sheet**: Usa `include_pending` ao chamar `account.calculate_balance()`
- **Income Statement**: Filtra journal entries por `state__in=['posted', 'pending']` quando `include_pending=True`
- **Cash Flow**: Usa `include_pending` ao calcular saldos inicial e final

### 2. Funções de Recálculo de Status

#### Função `recalculate_transaction_and_journal_entry_status`

Nova função completa em `accounting/utils.py` que:

1. **Verifica Balanceamento:**
   - Calcula totais de débitos e créditos
   - Atualiza flag `is_balanced`

2. **Atualiza Estado da Transação:**
   - `posted`: Todos os journal entries estão `posted`
   - `pending`: Todos os journal entries estão `pending`
   - `canceled`: Todos os journal entries estão `canceled`
   - `mixed`: Alguns `posted`, alguns `canceled`
   - `partial`: Alguns `posted`, alguns `pending`

3. **Atualiza Flags:**
   - `is_posted`: True se estado é `posted`
   - `is_balanced`: True se débitos = créditos
   - `is_reconciled`: True se todos os bank entries estão reconciliados

4. **Atualiza Journal Entry Flags:**
   - `is_cash`: True se tem `bank_account` ou `bank_designation_pending`
   - `is_reconciled`: True se tem reconciliação com status `matched` ou `approved`

**Uso:**
```python
from accounting.utils import recalculate_transaction_and_journal_entry_status

# Recalcular transações específicas
stats = recalculate_transaction_and_journal_entry_status(
    transaction_ids=[1, 2, 3]
)

# Recalcular todas as transações de uma empresa
stats = recalculate_transaction_and_journal_entry_status(
    company_id=123
)

# Recalcular todas as transações
stats = recalculate_transaction_and_journal_entry_status()
```

**Retorno:**
```python
{
    'transactions_checked': 100,
    'transactions_updated': 25,
    'journal_entries_updated': 50,
    'state_changes': 10
}
```

#### Tarefa Celery `recalculate_status_task`

Nova tarefa Celery para executar o recálculo de forma assíncrona:

```python
from accounting.tasks import recalculate_status_task

# Executar como tarefa assíncrona
result = recalculate_status_task.delay(
    transaction_ids=[1, 2, 3],
    company_id=123
)

# Verificar resultado
stats = result.get()
```

**Uso via API (se implementado):**
```json
POST /api/tasks/recalculate-status/
{
  "transaction_ids": [1, 2, 3],  // opcional
  "company_id": 123  // opcional
}
```

### 3. Função Existente Melhorada

#### `update_journal_entries_and_transaction_flags`

Função existente mantida para compatibilidade. Ela atualiza:
- Flags de journal entries (`is_cash`, `is_reconciled`)
- Flags de transações (`is_balanced`, `is_reconciled`)

**Nota:** Esta função não atualiza o estado (`state`) da transação, apenas as flags. Use `recalculate_transaction_and_journal_entry_status` para uma atualização completa.

## Quando Usar Cada Função

### `update_journal_entries_and_transaction_flags`
- Quando você já sabe que o estado está correto
- Apenas precisa atualizar flags (is_cash, is_reconciled, is_balanced)
- Mais rápida, menos completa

### `recalculate_transaction_and_journal_entry_status`
- Quando você precisa garantir que tudo está correto
- Quando estados podem estar inconsistentes
- Quando você quer uma atualização completa
- Mais lenta, mais completa

## Exemplos de Uso

### Gerar Relatório com Pending
```python
from accounting.services.financial_statement_service import FinancialStatementGenerator

generator = FinancialStatementGenerator(company_id=123)
statement = generator.generate_statement(
    template=template,
    start_date=date(2025, 1, 1),
    end_date=date(2025, 12, 31),
    include_pending=True  # Incluir pending
)
```

### Recalcular Status Após Importação
```python
from accounting.utils import recalculate_transaction_and_journal_entry_status

# Após importar transações
stats = recalculate_transaction_and_journal_entry_status(
    company_id=123
)
print(f"Atualizadas {stats['transactions_updated']} transações")
```

### Recalcular Status Via Celery
```python
from accounting.tasks import recalculate_status_task

# Executar em background
task = recalculate_status_task.delay(company_id=123)

# Verificar progresso
if task.ready():
    result = task.get()
    print(result)
```

## Migração

Se você já estava usando `recalc_unposted_flags_task`, ela ainda funciona, mas considere migrar para `recalculate_status_task` para uma atualização mais completa.

## Notas

- O recálculo de status é executado dentro de uma transação atômica para garantir consistência
- A função usa `select_for_update()` para evitar condições de corrida
- Journal entries são atualizados em batch para melhor performance
- A função retorna estatísticas detalhadas sobre o que foi atualizado


# 14 — Recursos Avançados

Este capítulo cobre funcionalidades avançadas da plataforma: base de conhecimento com IA, chat assistente, gerenciamento de tarefas assíncronas, índices financeiros e sistema de atividades.

---

## 14.1 Base de Conhecimento (Knowledge Base)

A base de conhecimento permite criar repositórios de documentos por empresa e fazer perguntas que são respondidas por IA (Gemini).

### Criar uma Base de Conhecimento

```bash
POST /acme/api/knowledge-bases/
{
  "name": "Manual Interno",
  "description": "Procedimentos e políticas da empresa"
}
```

### Upload de Documentos

```bash
POST /acme/api/knowledge-bases/{id}/documents/
Content-Type: multipart/form-data

file: manual_procedimentos.pdf
title: Manual de Procedimentos Operacionais
```

**Formatos suportados:** PDF, DOCX, TXT, MD

### Fazer Perguntas

```bash
POST /acme/api/knowledge-bases/{id}/ask/
{
  "question": "Qual é o procedimento para aprovação de despesas acima de R$ 5.000?"
}
```

**Resposta:**

```json
{
  "answer": "De acordo com o Manual de Procedimentos, despesas acima de R$ 5.000 devem...",
  "citations": [
    {
      "document": "Manual de Procedimentos Operacionais",
      "page": 12,
      "excerpt": "..."
    }
  ],
  "confidence": 0.92
}
```

### Feedback sobre Respostas

```bash
POST /acme/api/knowledge-bases/answers/{answer_id}/feedback/
{
  "rating": 5,
  "comment": "Resposta precisa e completa"
}
```

### Endpoints

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET/POST` | `/{tenant}/api/knowledge-bases/` | CRUD bases |
| `POST` | `/{tenant}/api/knowledge-bases/{id}/documents/` | Upload documentos |
| `GET` | `/{tenant}/api/documents/` | Listar documentos |
| `POST` | `/{tenant}/api/knowledge-bases/{id}/ask/` | Fazer pergunta |
| `POST` | `/{tenant}/api/knowledge-bases/answers/{id}/feedback/` | Feedback |

> **Pré-requisito:** Chave da API Gemini configurada no servidor (`GEMINI_API_KEY`).

---

## 14.2 Chat Assistente (AI Chat)

A plataforma oferece um assistente de IA integrado para perguntas sobre os dados da empresa.

### Perguntar com Contexto

```bash
POST /api/chat/ask/
{
  "question": "Qual foi o lucro operacional da Filial SP no último trimestre?",
  "tenant": "acme"
}
```

O chat usa o contexto dos dados da empresa (transações, contas, demonstrativos) para responder.

### Perguntar sem Contexto

```bash
POST /api/chat/ask_nocontext/
{
  "question": "Como funciona o regime tributário Simples Nacional?"
}
```

### Chat Flexível

O endpoint flexível permite configurar o comportamento do chat:

```bash
POST /api/chat/flexible/
{
  "question": "Analise as despesas de março",
  "context_type": "financial",
  "tenant": "acme",
  "date_range": {"start": "2026-03-01", "end": "2026-03-31"}
}
```

### Diagnóstico

```bash
POST /api/chat/diag/
```

Retorna informações sobre a configuração do chat (modelo, contexto disponível).

---

## 14.3 Gerenciamento de Tarefas (Jobs/Tasks)

Operações demoradas (conciliação, ETL, sync ERP, recálculos) são executadas em background via Celery. O sistema oferece APIs para acompanhar e controlar essas tarefas.

### Listar Tarefas

```bash
GET /api/tasks/
```

**Filtros:**

```bash
# Por status
GET /api/tasks/?status=running

# Por tipo
GET /api/tasks/?type=reconciliation
```

### Detalhe de uma Tarefa

```bash
GET /api/tasks/{task_id}/
```

**Resposta:**

```json
{
  "id": "abc123-def456",
  "type": "reconciliation",
  "status": "running",
  "progress": 65,
  "started_at": "2026-04-15T10:00:00Z",
  "details": {
    "total_records": 1500,
    "processed": 975
  }
}
```

### Parar uma Tarefa

```bash
POST /api/tasks/{task_id}/stop/
```

Envia um sinal de parada suave (soft stop). Se a tarefa não parar, um hard stop é aplicado após o timeout.

### Tipos de Tarefa

```bash
GET /api/tasks/types/
```

Lista todos os tipos de tarefa disponíveis no sistema.

### Estatísticas

```bash
GET /api/tasks/statistics/
```

Retorna métricas agregadas: tarefas por status, tempo médio de execução, taxa de sucesso.

### API Legada (Jobs)

Endpoints legados que ainda funcionam:

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/jobs/` | Listar jobs |
| `GET` | `/jobs/{task_id}/` | Detalhe do job |
| `POST` | `/jobs/{task_id}/cancel/` | Cancelar job |

---

## 14.4 Índices Financeiros

O sistema mantém um cadastro de índices financeiros (IGPM, IPCA, CDI, Selic, etc.) com cotações históricas e previsões.

### Índices

```bash
# Listar índices
GET /api/core/financial_indices/

# Detalhe de um índice
GET /api/core/financial_indices/{id}/
```

### Cotações

```bash
# Cotações de um índice
GET /api/core/financial_indices/{id}/quotes/

# Listar todas as cotações
GET /api/core/index_quotes/

# Criar cotação
POST /api/core/index_quotes/
{
  "financial_index": 1,
  "date": "2026-04-15",
  "value": 0.47
}
```

### Previsões

```bash
# Previsões de um índice
GET /api/core/financial_indices/{id}/forecast/

# Criar previsão
POST /api/core/index_forecasts/
{
  "financial_index": 1,
  "date": "2026-05-01",
  "value": 0.45,
  "confidence": 0.85
}
```

### Uso com Contratos

Índices financeiros são usados para reajuste de contratos. Ao vincular um contrato a um índice, o sistema calcula automaticamente o valor reajustado com base nas cotações.

### Previsão de Recorrências (RRULE)

```bash
POST /api/core/rrule_preview/
{
  "rrule": "FREQ=MONTHLY;COUNT=12;BYMONTHDAY=15",
  "start_date": "2026-01-15"
}
```

Retorna as próximas ocorrências da regra de recorrência — útil para contratos, cobranças e agendamentos.

---

## 14.5 Feed de Atividades (Activity Feed)

O sistema registra automaticamente ações dos usuários:

```bash
GET /api/activity/
```

**Eventos registrados:**
- Criação, edição e exclusão de registros
- Importações ETL
- Conciliações realizadas
- Sincronizações ERP
- Login/logout

**Filtros:**

```bash
# Atividades de um usuário
GET /api/activity/?user=5

# Atividades de um tipo
GET /api/activity/?verb=created

# Atividades recentes
GET /api/activity/?ordering=-created_at&page_size=20
```

---

## 14.6 Embeddings e Busca Semântica

O sistema usa **embeddings vetoriais** (pgvector) para busca por similaridade semântica.

### Onde São Usados

| Uso | Descrição |
|-----|-----------|
| **Conciliação** | Encontrar correspondências entre transações bancárias e lançamentos |
| **Sugestão de conta** | Sugerir conta contábil para novos lançamentos |
| **Busca** | Pesquisa por significado (não apenas texto exato) |

### Gerenciamento

```bash
# Verificar saúde
GET /acme/embeddings/health/

# Contar registros sem embedding
GET /acme/embeddings/missing-counts/

# Preencher embeddings faltantes
POST /acme/embeddings/backfill/

# Acompanhar tarefa de backfill
GET /acme/embeddings/tasks/{task_id}/

# Listar jobs de embedding
GET /acme/embeddings/jobs/

# Busca semântica
POST /acme/embeddings/search/
{"query": "pagamento de aluguel", "model": "Transaction", "limit": 10}

# Teste rápido
GET /acme/embeddings/test/
```

> **Avançado:** Embeddings são calculados automaticamente para novos registros. O backfill é necessário apenas para registros criados antes da ativação do recurso ou quando os vetores precisam ser recalculados.

---

## 14.7 Celery — Filas e Controle

Para operadores do sistema que precisam monitorar o processamento em background:

### Status das Filas

```bash
GET /api/celery/queues/
```

Retorna informações sobre as filas Celery (tamanho, workers ativos, etc.).

### Resultados de Tarefas

```bash
GET /api/celery/results/
```

### Controle de Tarefas Celery

```bash
# Pausar/retomar/revogar uma tarefa
POST /api/celery/tasks/{uuid}/{action}/
```

Ações possíveis: `revoke`, `terminate`.

---

## 14.8 Tutorial Integrado

A plataforma oferece um sistema de tutoriais integrado:

```bash
GET /api/tutorial/
```

Retorna guias passo a passo para operações comuns. Pode ser filtrado por módulo:

```bash
GET /api/tutorial/?module=reconciliation
GET /api/tutorial/?module=financial_statements
```

---

## 14.9 Introspecção da API (Meta)

O sistema possui uma camada completa de introspecção:

| Endpoint | Descrição |
|----------|-----------|
| `GET /api/meta/health/` | Status do sistema (sem autenticação) |
| `GET /api/meta/endpoints/` | Todos os endpoints com parâmetros |
| `GET /api/meta/models/` | Todos os modelos com campos |
| `GET /api/meta/models/{name}/` | Detalhe de um modelo |
| `GET /api/meta/models/{name}/relationships/` | Grafo de relacionamentos |
| `GET /api/meta/enums/` | Valores de enums/choices |
| `GET /api/meta/filters/` | Filtros disponíveis por endpoint |
| `GET /api/meta/capabilities/` | Capacidades do sistema |

> **Dica:** Use `/api/meta/endpoints/` para descobrir novos endpoints que foram adicionados ao sistema, e `/api/meta/models/` para entender a estrutura de dados sem precisar acessar o código.

---

*Anterior: [13 — Regras de Automação](13-regras-automacao.md) · Próximo: [15 — Referência da API](15-api-referencia.md)*

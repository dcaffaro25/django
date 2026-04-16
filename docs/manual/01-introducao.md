# 01 — Introdução à Plataforma Nord

## 1.1 O que é a Plataforma Nord?

A **Plataforma Nord** é um sistema de gestão empresarial (ERP) multi-tenant desenvolvido com **Django** e **Django REST Framework**. Ela foi projetada para atender empresas que precisam de:

- **Contabilidade** completa (plano de contas, lançamentos, transações, centros de custo)
- **Conciliação bancária** automatizada com inteligência artificial
- **Demonstrações financeiras** dinâmicas (DRE, balanço patrimonial, fluxo de caixa)
- **Faturamento** com suporte a NF-e (Nota Fiscal Eletrônica)
- **Gestão de RH** (cargos, folha de pagamento, KPIs, bônus)
- **Controle de estoque** (movimentações, custeio, valoração)
- **Integrações com ERPs** externos (Omie, entre outros)
- **Importação em massa** de dados via Excel (pipeline ETL)
- **Base de conhecimento** com IA generativa (Gemini)

---

## 1.2 Arquitetura Geral

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Plataforma Nord                              │
│                                                                      │
│   ┌─────────────┐  ┌──────────────┐  ┌────────┐  ┌──────────────┐  │
│   │Multi-tenancy │  │Contabilidade │  │   RH   │  │ Faturamento  │  │
│   │  Empresas    │  │  Plano Contas│  │ Folha  │  │   NF-e       │  │
│   │  Entidades   │  │  Conciliação │  │ KPIs   │  │   Faturas    │  │
│   │  Usuários    │  │  Dem. Financ.│  │        │  │   Parceiros  │  │
│   └──────┬───────┘  └──────┬───────┘  └───┬────┘  └──────┬───────┘  │
│          │                 │              │               │          │
│          └─────────────────┴──────────────┴───────────────┘          │
│                              │                                       │
│   ┌────────────┐  ┌─────────┴─────────┐  ┌─────────────┐           │
│   │  Estoque   │  │      Core         │  │Integrações  │           │
│   │ Moviment.  │  │  Tarefas / Chat   │  │  ERP (Omie) │           │
│   │  Custeio   │  │  Índices Financ.  │  │  Sincroniz. │           │
│   └────────────┘  └───────────────────┘  └─────────────┘           │
│                                                                      │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │            Camada de Introspecção (/api/meta/)               │   │
│   │   endpoints · modelos · enums · filtros · health            │   │
│   └─────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

### Componentes Principais

| Componente | Tecnologia | Função |
|-----------|------------|--------|
| **Backend** | Django 4.x + DRF | API REST, lógica de negócio, autenticação |
| **Banco de Dados** | PostgreSQL | Armazenamento persistente, pgvector para embeddings |
| **Tarefas Assíncronas** | Celery + Redis | Processamento em background (conciliação, ETL, sync ERP) |
| **Frontend** | React + Vite + shadcn/ui | Interface web do usuário |
| **Admin** | Django Admin | Interface administrativa para cadastros e operações |
| **IA** | Gemini API / Embeddings | Base de conhecimento, chat assistente, sugestões de conciliação |

---

## 1.3 Conceitos Fundamentais

### Multi-Tenancy (Múltiplos Inquilinos)

A plataforma suporta **múltiplas empresas** em uma única instalação. Cada empresa (tenant) possui:

- Seu próprio **subdomínio** (ex: `minha-empresa`)
- Dados **completamente isolados** das demais empresas
- URLs no formato `/{tenant}/api/...`

Por exemplo, se sua empresa tem o subdomínio `acme`, os endpoints ficam em:
```
https://servidor.com/acme/api/transactions/
https://servidor.com/acme/api/accounts/
```

### Entidades (Hierarquia Organizacional)

Dentro de cada empresa, é possível criar **entidades** organizadas em árvore hierárquica (MPTT). Exemplos:
- Grupo Empresarial → Empresa Controladora → Filial A, Filial B
- Holding → Subsidiária → Departamento

Entidades podem **herdar contas contábeis e centros de custo** da entidade-pai.

### Autenticação por Token

Toda comunicação com a API utiliza **tokens de autenticação**. Após o login, você recebe um token que deve ser enviado em todas as requisições:

```
Authorization: Token abc123def456...
```

---

## 1.4 Módulos Disponíveis

| Módulo | Descrição | Principais Funcionalidades |
|--------|-----------|---------------------------|
| **Contabilidade** | Gestão contábil completa | Plano de contas (árvore), transações, lançamentos contábeis, contas bancárias, centros de custo, alocações |
| **Conciliação** | Conciliação bancária inteligente | Pipeline configurável, sugestões automáticas via IA, regras personalizáveis, dashboard de acompanhamento |
| **Demonstrações Financeiras** | Relatórios contábeis | DRE detalhado, balanço patrimonial, fluxo de caixa, templates customizáveis, comparações entre períodos, exportação PDF/Excel |
| **Faturamento** | Gestão comercial e fiscal | Parceiros comerciais, produtos/serviços, contratos, faturas, importação/gestão de NF-e |
| **RH** | Recursos humanos | Cargos, funcionários, controle de ponto, KPIs, bônus, ajustes recorrentes, folha de pagamento |
| **Estoque** | Controle de inventário | Almoxarifados, movimentações (FIFO/média ponderada), camadas de estoque, alertas, valoração |
| **ETL** | Importação de dados | Pipeline para importação de planilhas Excel com transformações, mapeamento e validação |
| **Integrações ERP** | Conexão com ERPs externos | Sincronização com Omie (e outros), jobs automáticos, registros brutos, importação ETL |
| **Base de Conhecimento** | IA assistente | Bases de conhecimento por empresa, upload de documentos, perguntas e respostas com Gemini |
| **Tarefas** | Processamento assíncrono | Gerenciamento de jobs em background, status, cancelamento, estatísticas |

---

## 1.5 Formas de Acesso

A plataforma oferece **três formas de acesso** principais:

### 1. Interface Web (Frontend React)

A interface principal para operação do dia a dia. Acessível pelo navegador em:
```
https://servidor.com/{tenant}/
```

### 2. Painel Administrativo (Django Admin)

Interface de administração para cadastros, configurações avançadas e operações em lote. Acessível em:
```
https://servidor.com/admin/
```

> **Acesso:** Requer usuário com permissão `staff` ou `superuser`.

### 3. API REST

Para integrações programáticas, automações e acesso por sistemas externos:
```
https://servidor.com/{tenant}/api/...
```

Todos os endpoints seguem o padrão REST e retornam JSON.

---

## 1.6 Convenções de URL

| Padrão | Descrição | Exemplo |
|--------|-----------|---------|
| `/{tenant}/api/...` | Endpoint com escopo de empresa | `/acme/api/transactions/` |
| `/api/core/...` | Endpoint global (sem tenant) | `/api/core/users/` |
| `/api/meta/...` | Endpoint de introspecção | `/api/meta/endpoints/` |
| `/admin/` | Painel administrativo | `/admin/accounting/transaction/` |

### Formato de Dados

| Aspecto | Padrão |
|---------|--------|
| **Content-Type** | `application/json` |
| **Datas** | ISO 8601: `YYYY-MM-DD` (ex: `2026-04-15`) |
| **Data/Hora** | ISO 8601: `YYYY-MM-DDTHH:MM:SS.ffffffZ` |
| **Timezone** | UTC |
| **IDs** | Inteiros (`BigAutoField`) |
| **Barra final** | A maioria dos endpoints aceita com ou sem `/` final |

---

## 1.7 Próximos Passos

- **Se é sua primeira vez:** Vá para [02 — Primeiros Passos](02-primeiros-passos.md)
- **Se quer administrar cadastros:** Vá para [03 — Painel Administrativo](03-admin-django.md)
- **Se quer entender o módulo contábil:** Vá para [05 — Contabilidade](05-contabilidade.md)
- **Se quer importar dados de planilhas:** Vá para [11 — Importação ETL](11-etl-importacao.md)
- **Se quer configurar integração ERP:** Vá para [12 — Integrações ERP](12-integracoes-erp.md)

---

*Próximo: [02 — Primeiros Passos](02-primeiros-passos.md)*

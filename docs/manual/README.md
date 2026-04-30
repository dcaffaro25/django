# Manual do Usuário — Plataforma Nord

> **Versão:** 1.0 · **Atualizado em:** Abril 2026
> Plataforma multi-tenant de ERP, Contabilidade, Faturamento, RH e Estoque

---

## Sobre este Manual

Este manual foi criado para ajudar **administradores, contadores, analistas financeiros e operadores** a utilizarem a plataforma Nord no dia a dia. Ele cobre desde as operações mais básicas até configurações avançadas de integrações e automações.

---

## Índice

### Parte I — Fundamentos

| # | Capítulo | Descrição |
|---|----------|-----------|
| 01 | [Introdução](01-introducao.md) | Visão geral da plataforma, arquitetura e conceitos fundamentais |
| 02 | [Primeiros Passos](02-primeiros-passos.md) | Login, navegação, autenticação por token e configuração inicial |
| 03 | [Painel Administrativo (Django Admin)](03-admin-django.md) | Guia completo do painel de administração: cadastros, filtros, ações em lote |
| 04 | [Multi-Tenancy e Usuários](04-multitenancy-usuarios.md) | Empresas, entidades, hierarquia organizacional e gestão de usuários |

### Parte II — Módulos de Negócio

| # | Capítulo | Descrição |
|---|----------|-----------|
| 05 | [Contabilidade](05-contabilidade.md) | Plano de contas, transações, lançamentos contábeis, contas bancárias, centros de custo |
| 06 | [Conciliação Bancária](06-conciliacao-bancaria.md) | Pipeline de conciliação, sugestões automáticas, regras, dashboard |
| 07 | [Demonstrações Financeiras](07-demonstracoes-financeiras.md) | Templates, DRE, balanço patrimonial, fluxo de caixa, comparações |
| 08 | [Faturamento e NF-e](08-faturamento-nfe.md) | Parceiros comerciais, produtos/serviços, contratos, faturas, nota fiscal eletrônica |
| 09 | [Recursos Humanos](09-rh-folha.md) | Cargos, funcionários, ponto, KPIs, bônus, folha de pagamento |
| 10 | [Estoque](10-estoque.md) | Almoxarifados, movimentações, custeio, alertas, valoração |

### Parte III — Integrações e Automações

| # | Capítulo | Descrição |
|---|----------|-----------|
| 11 | [Importação de Dados (ETL)](11-etl-importacao.md) | Pipeline ETL para importação de planilhas Excel |
| 12 | [Integrações ERP](12-integracoes-erp.md) | Conexão com Omie e outros ERPs, sincronização automática |
| 13 | [Regras de Automação](13-regras-automacao.md) | Regras de substituição (de-para) e regras de integração |
| 14 | [Recursos Avançados](14-recursos-avancados.md) | Base de conhecimento IA, chat, tarefas assíncronas, embeddings |

### Parte IV — Referência

| # | Capítulo | Descrição |
|---|----------|-----------|
| 15 | [Referência da API](15-api-referencia.md) | Catálogo completo de endpoints, parâmetros e exemplos |
| 16 | [Grupos de Parceiros](16-grupos-parceiros.md) | Consolidação de matriz/filiais/CPF/adquirentes via Groups e Aliases auto-aprendidos |

---

## Convenções do Manual

| Símbolo | Significado |
|---------|-------------|
| `GET`, `POST`, etc. | Método HTTP |
| `/{tenant}/api/...` | URL com prefixo do tenant (subdomínio da empresa) |
| `< >` | Valor variável (substituir pelo real) |
| **Dica** | Sugestão para facilitar o uso |
| **Atenção** | Cuidado para evitar erros |
| **Avançado** | Funcionalidade para usuários experientes |

---

## Documentação Complementar

Além deste manual, o projeto possui documentação técnica detalhada:

| Pasta | Conteúdo |
|-------|----------|
| `docs/architecture/` | Documentação técnica aprofundada (reconciliação, demonstrações financeiras, ETL, etc.) |
| `docs/dev/` | Guias de desenvolvimento local, deploy Railway, variáveis de ambiente |
| `docs/inventory/` | Manual técnico de estoque e walkthrough de NF-e |
| `docs/archive/` | Documentos de planejamento e migração Retool (histórico) |
| `OPENCLAW_API_MANUAL.md` | Manual de integração para o agente OpenClaw |

---

*Nord Ventures © 2026*

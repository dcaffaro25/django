# 16 — Grupos de Parceiros (Business Partner Groups)

Consolide múltiplas identidades fiscais (matriz + filiais, CNPJs distintos
do mesmo grupo econômico, CPF de sócio que paga pela PJ, adquirentes
como Cielo / Stone / Mercado Livre) em **um único ator econômico** para
fins de relatório, sem alterar os cadastros originais.

O sistema **aprende** os grupos a partir de ações que o operador já faz
no dia-a-dia — aceitar vínculos NF↔Tx, finalizar conciliações banco↔livro
e anexar Invoices a NFs. Nenhum cadastro manual é necessário; o usuário
apenas confirma sugestões quando elas surgem.

---

## 16.1 Conceitos

### Por que `cnpj_root` não basta

A "raiz" de 8 dígitos do CNPJ já une matriz e filiais de uma mesma pessoa
jurídica (resolvido em [`BusinessPartner.cnpj_root`](08-faturamento-nfe.md)).
Mas existem três cenários que `cnpj_root` **não** cobre:

| Cenário | Exemplo | Como `cnpj_root` falha |
|---------|---------|-----------------------|
| Grupo econômico cross-root | "Petrobras Distribuidora" e "Petrobras Refino" — raízes diferentes | raízes não batem |
| CPF ↔ CNPJ | Sócio paga conta da PJ pelo CPF dele | tipos de documento diferentes |
| Adquirente / marketplace | Extrato banco mostra CNPJ da Cielo, NF é do cliente real | partes não relacionadas |

Para cada um existem dois primitivos complementares:

- **`BusinessPartnerGroup`** — agrupa **dois ou mais BPs cadastrados**
  num único ator econômico. Cada grupo tem um **`primary_partner`** que
  é o "rosto" do grupo nos relatórios consolidados.
- **`BusinessPartnerAlias`** — apelida uma **string** observada
  externamente (CNPJ no extrato bancário) para um BP cadastrado. Útil
  quando uma das pontas não tem cadastro próprio (caso do adquirente).

### Estado de revisão

Tanto memberships quanto aliases têm a mesma máquina de estados de
`NFTransactionLink`:

```
suggested  →  accepted  (auto ou manual)
suggested  →  rejected  (manual ou conflito)
rejected   →  suggested (re-aprendido)
```

Apenas memberships **`accepted`** consolidam relatórios. Sugestões ficam
visíveis na fila de revisão mas não afetam números.

### Invariantes garantidas no DB

Constraints parciais (Postgres) impedem inconsistências silenciosas:

- **Um BP em no máximo um Group ativo**: `(business_partner)` único onde
  `review_status='accepted'`.
- **Um único `primary` por Group**: `(group)` único onde `role='primary'`.
- **Um alias aceito por (tenant, identifier)**: `(company, alias_identifier)`
  único onde `review_status='accepted'`.

Se uma operação tentar violar qualquer um dos três, o DB recusa — o
sistema nunca fica em estado ambíguo.

---

## 16.2 Como sugestões nascem (os hooks)

O sistema observa ações do operador e gera sugestões automaticamente. Há
**três pontos de captura para Groups** e **um para Aliases**.

| Hook | Quando dispara | Tipo de sugestão | Confiança padrão |
|------|----------------|------------------|------------------|
| `nf_link_service.accept_link` | Operador aceita um vínculo NF↔Tx onde `Tx.cnpj` resolve para BP_a e a contraparte da NF é BP_b ≠ BP_a | Group | Confiança do próprio link |
| `accounting.views finalize_reconciliation_matches` (v1 + legacy) | Conciliação banco↔livro finaliza; CNPJ do extrato resolve para BP_a, CNPJ do livro para BP_b ≠ BP_a | Group | 0.85 |
| Mesmo hook, mas só **um lado resolve** para BP | "CNPJ banco não tem BP cadastrado, mas CNPJ livro tem" → aprende alias | Alias | 0.7 |
| `nf_invoice_sync.attach_invoice_to_nf` | Operador anexa uma Invoice cuja `partner` ≠ contraparte da NF | Group | 0.75 |

Todos os hooks são **best-effort** — embrulhados em try/except, nunca
quebram a operação principal. Se a sugestão falhar (por bug ou estado
inválido), o vínculo / conciliação / anexo ainda completa normalmente.

### Idempotência

Cada sugestão registra `(method, source_id)` no array `evidence`. A
mesma fonte aceita 2× **não** infla `hit_count` — só sinais de fontes
distintas contam para auto-promoção.

### Auto-promoção (thresholds)

| Tipo | Threshold | Justificativa |
|------|-----------|---------------|
| **Group** | **3 hits** | Filtra coincidências (ex: um único depósito Cielo dividido entre dois clientes) sem demorar demais |
| **Alias** | **5 hits** | Adquirentes legitimamente recebem por múltiplos clientes; só consolida com várias confirmações |
| **Merge** (cross-Group) | **Nunca auto** | Mesclar dois grupos existentes é decisão de relatório — exige clique manual |

Ao promover, o sistema **rejeita automaticamente** sugestões conflitantes
do mesmo BP em outros grupos (mantém a invariante "um BP em no máximo
um Group ativo").

---

## 16.3 Tour da UI — Tela `/billing/grupos`

Aba **Grupos** dentro do hub de Faturamento. Mostra um badge com a
quantidade de sugestões pendentes — operadores chegam aqui para limpar
fila.

### Sub-aba **Sugestões**

Lista cards de sugestões "puras" (não-merge) pendentes de revisão. Cada
card mostra:

- **Tipo** — chip "grupo" (azul). Cards de mesclagem aparecem na sub-aba
  Mesclagens.
- **Confiança** — `ConfidenceBadge` colorido por banda
  (verde ≥ 85%, âmbar 60–85%, cinza < 60%).
- **Hits** — quantos sinais distintos sustentam a sugestão.
- **Bloco esquerdo: "adicionar a"** — nome do grupo que receberá o BP.
  Para sugestões em grupo novo (Caso 3) o nome é o do BP primary.
- **Bloco direito: "parceiro"** — nome do BP a ser adicionado, com
  pílula de tipo (cliente/fornecedor/ambos) e CNPJ formatado.
- **Botões** — `Aceitar` (verde) confirma e move para `accepted`.
  `Rejeitar` (cinza) move para `rejected` (não some — fica auditável).

### Sub-aba **Mesclagens**

Mesma listagem, mas filtrada por `merge_only=1` — apenas sugestões em
que **ambos os BPs já estão em grupos diferentes**. Aceitar uma
mesclagem ainda **não** funde os grupos: ela apenas marca aquele
membership como aceito. A fusão real é uma operação separada na sub-aba
Grupos (botão "Mesclar para cá").

Esse passo extra é deliberado: mesclar grupos é decisão de consolidação
em relatórios e merece confirmação intencional.

### Sub-aba **Grupos**

Lista todos os grupos ativos do tenant. Cada linha é colapsável (chevron
à esquerda) com header:

- Coroa âmbar (ícone do primary)
- Nome do grupo (= nome do primary)
- CNPJ raiz formatado
- Texto à direita: `N aceitos · M total` (todos os memberships, inclui
  pendentes e rejeitados para auditoria)

**Ao expandir** o grupo, três blocos aparecem:

1. **Membros** — cada BP aceito do grupo, com:
   - Coroa para o primary
   - Nome + pílula de tipo + CNPJ
   - Para não-primaries: botão de coroa que **promove a primary**.
     Promoção troca o `role` do antigo primary para `member` e move a
     coroa, atualizando também `BusinessPartnerGroup.name` e
     `primary_partner_id`. Operação atômica.

2. **Sugestões pendentes** (se houver) — sugestões em estado `suggested`
   apontando para este grupo, com botões de aceitar/rejeitar inline e
   chip de cor (azul = grupo, âmbar = merge).

3. **Mesclar para cá** — input numérico + botão. Digite o ID do grupo
   **origem** (que será absorvido) e clique. O grupo origem desaparece;
   seus membros migram para este grupo como `member` (o primary do
   origem perde o título mas mantém o vínculo). Esta é a forma manual
   de aceitar uma mesclagem que estava na fila de Mesclagens.

### Sub-aba **Apelidos**

Para revisão de `BusinessPartnerAlias`. Três botões de filtro no topo
trocam o `review_status` exibido (Sugeridos / Aceitos / Rejeitados).

Cada linha mostra:

- Ícone de tag
- `<CNPJ alias>` → `<Nome do BP>` (mais coroa de confiança e contagem
  de hits)
- Linha secundária: `BP <identifier real> · fonte <bank_reconciliation>`
- Botões `Aceitar` e `Rejeitar` quando `review_status='suggested'`

**Atenção** — aceitar um alias é decisão sensível. Uma vez aceito, ele
participa do *scoring* de matching futuro (boost +0.18 em
`nf_link_service._score`), o que pode acelerar reconhecimento mas
também propagar erros se o alias estiver errado. Em caso de dúvida,
rejeite e deixe o operador re-confirmar manualmente nos próximos
matches.

---

## 16.4 Indicador de Grupo no drawer do Parceiro

Ao abrir o drawer de edição de um BP (`/billing/parceiros` → clique na
linha), uma nova seção **Grupo** aparece logo acima dos cross-links de
Faturas / NFs.

- **Cabeçalho** — ícone de network + "Grupo: \<nome>". Se este BP é
  o primary, aparece pílula âmbar com coroa "primary"; se é membro,
  pílula cinza "membro".
- **Lista de irmãos** — outros BPs aceitos do mesmo grupo, com coroa
  para o primary. Cada linha mostra nome + CNPJ.
- **Link "Gerenciar grupo →"** — leva direto para `/billing/grupos`.

Se o BP não pertence a nenhum grupo, a seção inteira não é renderizada
(detecção via `bp.group_id == null` no payload, sem requisições extras).

---

## 16.5 Endpoint consolidado — `/api/business_partners/consolidated/`

Para listas que precisam mostrar **um BP por ator econômico** (padrão
"Leroy Merlin": um nome visível com chevron expandindo as filiais), use:

```
GET /<tenant>/api/business_partners/consolidated/?partner_type=client&search=leroy
```

**Query params:**

| Param | Valores | Descrição |
|-------|---------|-----------|
| `partner_type` | `client`, `vendor`, `both` | Filtra tipo |
| `is_active` | `1`, `0` | Ativos / inativos |
| `search` | string | Substring em `name` ou `identifier` |

**Resposta:**

```json
{
  "count": 2,
  "results": [
    {
      "kind": "group",
      "primary": { "id": 412, "name": "Leroy Merlin SP", "...": "..." },
      "members": [
        { "id": 511, "name": "Leroy Merlin RJ", "...": "..." },
        { "id": 723, "name": "Leroy Merlin BH", "...": "..." }
      ],
      "group_id": 17
    },
    {
      "kind": "standalone",
      "primary": { "id": 99, "name": "BP sem grupo", "...": "..." },
      "members": [],
      "group_id": null
    }
  ]
}
```

A serialização adiciona três campos read-only ao `BusinessPartnerSerializer`
para qualquer listagem regular:

- `group_id` — id do grupo aceito (ou `null`)
- `group_primary_partner_id` — id do BP primary do grupo
- `group_role` — `"primary"` | `"member"` | `null`

---

## 16.6 Operações manuais de manutenção

### Promover outro BP a primary

Pela UI: aba Grupos → expandir grupo → botão coroa na linha do membro
desejado.

Pela API:

```bash
POST /<tenant>/api/business-partner-groups/<group_id>/promote-primary/
{ "membership_id": <id-do-membership-aceito-a-promover> }
```

O membership precisa estar `accepted`. A operação:

1. Troca o `role` do antigo primary para `member`.
2. Promove o membership escolhido para `primary`.
3. Atualiza `group.primary_partner_id` e `group.name` para refletir o
   novo primary.

Tudo numa transação atômica.

### Mesclar dois grupos existentes

Pela UI: aba Grupos → expandir grupo destino → digitar ID do grupo
origem → "Mesclar para cá".

Pela API:

```bash
POST /<tenant>/api/business-partner-groups/<target_id>/merge/
{ "source_group_id": <source_id> }
```

Comportamento:

- Cada membership do grupo origem migra para o grupo destino com
  `role='member'`.
- Se um BP já é membro do destino, o membership do origem é descartado
  (sem duplicar).
- O grupo origem é **deletado** ao final (cascade nos memberships
  remanescentes — nesse ponto já estão migrados ou descartados).

### Aceitar / rejeitar um membership ou alias

```bash
POST /<tenant>/api/business-partner-group-memberships/<id>/accept/
POST /<tenant>/api/business-partner-group-memberships/<id>/reject/
POST /<tenant>/api/business-partner-aliases/<id>/accept/
POST /<tenant>/api/business-partner-aliases/<id>/reject/
```

Aceitar um alias **falha com 409** se outro alias aceito já reivindica
o mesmo `(company, alias_identifier)` — você precisa rejeitar o
concorrente primeiro.

---

## 16.7 Backfill retroativo

Para tenants que já acumularam `NFTransactionLink` aceitos antes de
a feature existir, há um management command que replays os links e
gera sugestões de Group:

```bash
# Simulação (não escreve nada)
python manage.py backfill_bp_groups --tenant evolat --dry-run

# Aplicar
python manage.py backfill_bp_groups --tenant evolat

# Todos os tenants
python manage.py backfill_bp_groups --all-tenants

# Com limite (útil para testes)
python manage.py backfill_bp_groups --tenant evolat --limit 100
```

Saída por tenant:

```
=== Tenant evolat (id=5) ===
  inspected=515 suggested=87 same_bp=412 unresolved=16 errors=0
```

| Contador | Significa |
|----------|-----------|
| `inspected` | Links aceitos avaliados |
| `suggested` | Pares (BP_a, BP_b) com BPs distintos → upsert chamado |
| `same_bp` | Tx e NF resolvem para o mesmo BP — sem sugestão |
| `unresolved` | Tx ou NF não resolvem para BP — sem sugestão |
| `errors` | Falhas no upsert (logado em stderr) |

**Idempotência:** rodar 2× não infla contadores no DB porque o
`evidence` array dedupe por `(method, source_id)`.

---

## 16.8 Cenários comuns

### "Um cliente novo abriu uma filial — devo criar um grupo?"

Não. Filiais com a mesma raiz de CNPJ já são unidas via `cnpj_root` em
toda lógica de matching e self-billing — sem precisar de Group. Group é
para casos **cross-root**.

### "Aceitei uma sugestão por engano. Como desfazer?"

Pela UI: aba Grupos → expandir grupo → não há botão direto; é preciso
remover via API:

```bash
DELETE /<tenant>/api/business-partner-group-memberships/<id>/
```

Ou rejeite o membership manualmente:

```bash
POST /<tenant>/api/business-partner-group-memberships/<id>/reject/
```

Rejeitar **não** apaga o membership — o histórico (incluindo
`evidence`) fica auditável.

### "Tem uma sugestão de mesclagem que está errada"

Rejeite o membership da fila de Mesclagens. O grupo origem permanece
intacto. Se a mesma sugestão ressurgir várias vezes, considere se há um
padrão de transação que está confundindo o matcher (por exemplo, um
alias incorreto aceito anteriormente que está enviesando o
`nf_link_service._score`).

### "Adquirente novo aparecendo no extrato — vou ter que aprender 5 vezes?"

Sim, por design. O threshold de 5 hits para aliases é mais conservador
que Groups (3) porque adquirentes legitimamente recebem por múltiplos
clientes — uma única ocorrência poderia consolidar um cliente errado
permanentemente. Cinco confirmações independentes filtram bem o ruído.

Se quiser acelerar, basta aceitar manualmente o alias na sub-aba
Apelidos depois da primeira sugestão — não é preciso esperar bater o
threshold.

### "Como ver o impacto de uma alias na próxima rodada de matching?"

Aliases aceitas alimentam `nf_link_service._score` com boost
**+0.18** quando a CNPJ da Tx (lado banco) é alias de algum BP
candidato (lado fiscal). O efeito aparece na próxima execução de:

```bash
python manage.py rescan_nf_links --tenant <sub>
```

Confirme procurando `cnpj_alias` no array `matched_fields` dos novos
`NFTransactionLink` criados.

---

## 16.9 Resumo da API

Todos os endpoints respeitam o prefixo de tenant (`/<sub>/api/…`).

### Groups

| Método | URL | Descrição |
|--------|-----|-----------|
| GET | `/business-partner-groups/` | Listar (filtros: `is_active`, `business_partner`) |
| GET | `/business-partner-groups/<id>/` | Detalhe com memberships embutidos |
| POST | `/business-partner-groups/` | Criar manualmente (raro) |
| PATCH | `/business-partner-groups/<id>/` | Editar nome / descrição |
| DELETE | `/business-partner-groups/<id>/` | Apagar (cascateia memberships) |
| POST | `/business-partner-groups/<id>/promote-primary/` | `{membership_id}` |
| POST | `/business-partner-groups/<id>/merge/` | `{source_group_id}` |

### Memberships

| Método | URL | Descrição |
|--------|-----|-----------|
| GET | `/business-partner-group-memberships/` | Listar (filtros: `review_status`, `group`, `business_partner`, `merge_only`) |
| POST | `/business-partner-group-memberships/<id>/accept/` | |
| POST | `/business-partner-group-memberships/<id>/reject/` | |
| DELETE | `/business-partner-group-memberships/<id>/` | Remove membership do grupo |

### Aliases

| Método | URL | Descrição |
|--------|-----|-----------|
| GET | `/business-partner-aliases/` | Listar (filtros: `review_status`, `business_partner`) |
| POST | `/business-partner-aliases/<id>/accept/` | (409 em conflito) |
| POST | `/business-partner-aliases/<id>/reject/` | |

### Listagem consolidada

| Método | URL | Descrição |
|--------|-----|-----------|
| GET | `/business_partners/consolidated/` | Linha por ator econômico |

---

*Capítulo 16 — Documentação Nord · 2026*

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

### Um único primitivo: `BusinessPartnerGroup`

Toda consolidação fiscal — matriz/filial, grupo econômico cross-CNPJ,
CPF de sócio pagando pela PJ — passa pelo mesmo modelo
**`BusinessPartnerGroup`**. Cada grupo tem um **`primary_partner`** que
é o "rosto" usado nos relatórios consolidados, e zero ou mais
*memberships* aceitos vinculando outros BPs ao grupo.

Cobre os três cenários típicos:

| Cenário | Exemplo | Como vira Group |
|---------|---------|-----------------|
| Matriz + filiais (mesmo CNPJ raiz) | Filiais do Mateus Supermercados em RJ, MA, CE… | **Auto-criado** ao salvar o segundo BP que compartilha a raiz |
| Grupo econômico cross-root | "Petrobras Distribuidora" e "Petrobras Refino" — raízes diferentes | Sugerido pelos hooks (NF↔Tx, conciliação) e aceito ao bater threshold |
| CPF ↔ CNPJ | Sócio paga conta da PJ pelo CPF dele | Sugerido pelos mesmos hooks; aceito após N confirmações |

`cnpj_root` continua existindo como uma coluna indexada de 8 dígitos no
`BusinessPartner` (usado pelo motor de matching de NF, self-billing
guard, etc.) — mas ela **não é mais a unidade de consolidação**: ela
apenas alimenta a auto-criação de Groups.

### `BusinessPartnerAlias` — quando uma das pontas não tem BP

Para o caso de **adquirentes / marketplaces** (Cielo, Stone, Mercado
Livre), o lado bancário traz um CNPJ que não corresponde a nenhum BP
cadastrado — só ao adquirente. Aqui usamos `BusinessPartnerAlias`,
que apelida uma **string** observada externamente para um BP existente.
Aliases não criam grupos; alimentam o boost de scoring no
`nf_link_service._score` para que matches futuros consigam casar
"depósito Cielo" com a NF do cliente real.

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

## 16.2 Como Groups são criados

Há **dois caminhos** que materializam um Group:

### Auto-criação por raiz CNPJ (estrutural)

`BusinessPartner.save()` chama `ensure_root_group(bp)` após persistir.
Quando `bp.cnpj_root` tem 2+ siblings no tenant (matriz + ao menos uma
filial), o sistema:

1. Verifica se já existe um Group para essa raiz (busca via qualquer
   sibling com membership aceito).
2. Se sim → adiciona o BP corrente como `member` aceito daquele Group.
3. Se não → cria um Group novo com o BP de id mais antigo como
   `primary` e adiciona todos os siblings como `member` aceitos.

Idempotente: salvar o mesmo BP duas vezes não duplica nada. Best-effort:
falha silenciosa em logs, sem nunca quebrar o save.

Na importação de NF-e (que cria BPs automaticamente quando vê um CNPJ
novo) isso significa que o segundo BP de um root produz o Group sem
intervenção do operador. A aba **Grupos** já mostra a relação na
próxima atualização.

### Sugestões aprendidas (cross-root, CPF, etc.)

Para casos onde a auto-criação por raiz não se aplica, o sistema
observa três ações do operador e gera *sugestões* — que viram aceitas
após batem o threshold ou aprovação manual.

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

A página tem **cinco sub-abas**:

### Sub-aba **Grupos** (default)

Lista todos os grupos ativos do tenant — auto-criados (matriz/filial)
e curados (cross-CNPJ, CPF). Cada linha é colapsável (chevron à
esquerda) com header:

- Coroa âmbar (ícone do primary)
- Nome do grupo (= nome do primary)
- CNPJ raiz formatado
- Texto à direita: `N aceitos · M total` (todos os memberships, inclui
  pendentes e rejeitados para auditoria)

**Ao expandir** o grupo, três blocos aparecem:

1. **Membros aceitos** — cada BP do grupo, com coroa para o primary,
   tipo, CNPJ. Botão de coroa em não-primaries promove o BP a primary
   atomicamente.
2. **Sugestões pendentes** (se houver) — sugestões em estado `suggested`
   apontando para este grupo, com aceitar/rejeitar inline.
3. **Mesclar para cá** — input numérico + botão. Digite o ID do grupo
   **origem** e clique para absorvê-lo.

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

### Sub-aba **Raiz CNPJ**

Diagnóstico para clusters de BPs que **deveriam** estar materializados
em Group mas ainda não estão (ex: um BP solto recém-importado antes do
hook rodar, ou um cluster que perdeu seu Group por exclusão manual).

Cada cluster mostra:

- Pílula "automático" (azul)
- Nome do BP mais antigo + raiz CNPJ + contagem
- Botão **Materializar** (estrela) — cria o Group ali mesmo, com o
  primary sendo o BP mais antigo e os demais como membros aceitos

Em estado normal (após `BusinessPartner.save` rodar para todos os BPs
do tenant), esta aba fica **vazia** com a mensagem "todos os
matriz/filial já estão materializados em grupos curados".

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

Para tenants que já existiam antes de a feature ser instalada, um
management command roda **dois passes** sequenciais:

```bash
# Simulação (não escreve nada)
python manage.py backfill_bp_groups --tenant evolat --dry-run

# Aplicar (ambos os passes)
python manage.py backfill_bp_groups --tenant evolat

# Apenas pass 1 (matriz/filial)
python manage.py backfill_bp_groups --tenant evolat --skip-links

# Apenas pass 2 (cross-root via NF↔Tx)
python manage.py backfill_bp_groups --tenant evolat --skip-roots

# Todos os tenants
python manage.py backfill_bp_groups --all-tenants
```

Saída por tenant:

```
=== Tenant evolat (id=5) ===
  [1/2] Materializing cnpj_root clusters…
    bps_visited=1224 groups_touched=50 errors=0
  [2/2] Replaying accepted NF↔Tx links…
    inspected=515 suggested=87 same_bp=412 unresolved=16 errors=0
```

| Pass | Contador | Significa |
|------|----------|-----------|
| 1 | `bps_visited` | BPs com `cnpj_root` não-vazio inspecionados |
| 1 | `groups_touched` | Groups criados ou estendidos por raiz |
| 2 | `inspected` | Links aceitos avaliados |
| 2 | `suggested` | Pares (BP_a, BP_b) com BPs distintos → upsert chamado |
| 2 | `same_bp` | Tx e NF resolvem para o mesmo BP — sem sugestão |
| 2 | `unresolved` | Tx ou NF não resolvem para BP — sem sugestão |

**Idempotência:** rodar 2× não duplica state. Pass 1 detecta Groups
existentes; pass 2 dedupe por `(method, source_id)` no array `evidence`.

Após o backfill, `BusinessPartner.save()` mantém o pass 1 atualizado
automaticamente — não é preciso re-rodar a menos que o sistema seja
restaurado de um snapshot anterior à feature.

---

## 16.8 Cenários comuns

### "Um cliente novo abriu uma filial — devo criar um grupo?"

Não. Quando você cadastra (ou importa) o BP da filial, o
`BusinessPartner.save()` detecta que outro BP do mesmo tenant
compartilha os 8 primeiros dígitos do CNPJ e **cria o Group
automaticamente** (ou adiciona a filial ao Group existente, se a matriz
já estiver em um). Você pode verificar imediatamente em `/billing/grupos`.

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
| GET | `/business-partner-groups/cnpj-root-clusters/` | Lista clusters de raiz CNPJ ainda não materializados |
| POST | `/business-partner-groups/materialize-cnpj-root/` | `{cnpj_root}` — promove um cluster (idempotente) |

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

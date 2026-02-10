# Engine NFe XML → Excel

Engine em Python que processa XMLs de **Nota Fiscal Eletrônica (NFe)** em uma pasta e gera um **arquivo Excel** com abas separadas, preservando a hierarquia e permitindo vincular itens à NF pela coluna `chave_NF`.

## Modelo de dados avaliado

Os XMLs da pasta fornecida são todos **NFe padrão brasileiro** (Portal da NF-e):

- **Formato:** `nfeProc` (NFe + protocolo de autorização) ou NFe direto
- **Versão:** 4.00
- **Namespace:** `http://www.portalfiscal.inf.br/nfe`
- **Arquivos:** `*-procNFe.xml` (nome com chave da NF no nome do arquivo)

Não há “modelos diferentes” de nota na pasta: todas seguem o mesmo layout NFe 4.00, com variação apenas em tags opcionais (por exemplo tipo de ICMS/PIS/COFINS, presença de transporte, cobrança, etc.).

## Abas do Excel gerado (agrupadas)

| Aba | Conteúdo | Vínculo |
|-----|----------|--------|
| **NFe** | Uma linha por nota: identificação (ide), emitente, destinatário, totais (vNF, vProd, vICMS…), observações, **totais da NF** e **dados do protocolo SEFAZ** (nProt, cStat, xMotivo) | `chave_NF` (44 dígitos) |
| **Itens** | Uma linha por item/produto: código, descrição, NCM, CFOP, quantidade, valor, impostos do item | `chave_NF` + `nItem` |
| **Financeiro** | Duplicatas (nDup, dVenc, vDup) e formas de pagamento (tPag, vPag). Coluna **tipo**: "Duplicata" ou "Pagamento" | `chave_NF` |
| **Transporte** | Frete, transportadora, volumes | `chave_NF` |
| **Referencias** | Referências a outras NFs (refNFe / refNF) | `chave_NF` |

Os **produtos** na aba **Itens** ficam vinculados à **NF** pela coluna **`chave_NF`**; em cada NF pode haver vários itens (`nItem` 1, 2, 3…).

## Uso

Na raiz do projeto (pasta `django`):

```bash
python scripts/run_nfe_to_excel.py "C:\caminho\para\pasta\com\XMLs" --output saida.xlsx
```

Opções:

- **`--output` / `-o`:** Caminho do Excel de saída (padrão: `NFe_consolidado.xlsx` na mesma pasta dos XMLs).
- **`--glob`:** Padrão de arquivos (padrão: `*.xml`). Ex.: `*-procNFe.xml` para só procNFe.

Exemplo:

```bash
python scripts/run_nfe_to_excel.py "C:\Users\...\NFs\Omie\2025.01\XML" -o NFe_consolidado_2025_01.xlsx --glob "*-procNFe.xml"
```

## Estrutura do código

- **`scripts/nfe_engine/parser.py`** – Parse de um XML (string/arquivo); retorna dicionário com listas por “tabela” (nfe, itens, totais, transporte, duplicatas, pagamento, referencias, protocolo).
- **`scripts/nfe_engine/excel_export.py`** – Agrega resultados de vários XMLs e grava um único `.xlsx` com uma aba por entidade.
- **`scripts/run_nfe_to_excel.py`** – CLI: varre a pasta, chama o parser e a exportação.

## Dependências

- **pandas** e **openpyxl** (já no `requirements.txt` do projeto).

## Uso programático

```python
from scripts.nfe_engine import parse_nfe_file, export_to_excel
from pathlib import Path

pasta = Path(r"C:\...\XML")
dados = []
for arq in pasta.glob("*-procNFe.xml"):
    r = parse_nfe_file(arq)
    if r:
        dados.append(r)
export_to_excel(dados, "saida.xlsx")
```

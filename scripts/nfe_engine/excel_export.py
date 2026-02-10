# -*- coding: utf-8 -*-
"""
Exporta dados extraídos de NFe para um arquivo Excel com abas agrupadas.
Cada aba corresponde a um grupo lógico (NFe, Itens, Financeiro, etc.),
com chave_NF para vincular itens e demais detalhes à nota fiscal.
"""
from pathlib import Path
from typing import List, Optional, Union

import pandas as pd


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Garante colunas em ordem consistente e sem duplicatas."""
    df = df.dropna(axis=1, how="all")
    return df


def _column_order(cols: List[str], priority: List[str]) -> List[str]:
    """Colunas na ordem: priority primeiro, depois o restante alfabético."""
    first = [c for c in priority if c in cols]
    rest = sorted([c for c in cols if c not in priority])
    return first + rest


def export_to_excel(
    list_of_data: List[dict],
    output_path: Union[str, Path],
    *,
    engine: str = "openpyxl",
    max_inf_cpl_len: Optional[int] = 500,
) -> Path:
    """
    Recebe uma lista de dicionários retornados por parse_nfe_xml/parse_nfe_file
    (um por arquivo processado) e gera um único Excel com abas agrupadas.

    Abas (agrupadas):
      - NFe: cabeçalho + totais + protocolo (uma linha por NF).
      - Itens: produtos/serviços; chave_NF + nItem vinculam à NF.
      - Financeiro: duplicatas e formas de pagamento (coluna "tipo": Duplicata | Pagamento).
      - Transporte: dados de frete/volumes.
      - Referencias: NFref (refNFe, refNF).

    Args:
        list_of_data: lista de dicts com chaves nfe, itens, totais, transporte, duplicatas, pagamento, referencias, protocolo.
        output_path: caminho do arquivo .xlsx de saída.
        engine: engine do Excel (openpyxl).
        max_inf_cpl_len: não usado; reservado para truncar textos longos.

    Returns:
        Path do arquivo gerado.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # ---- Aba NFe: merge cabeçalho + totais + protocolo (uma linha por NF) ----
    nfe_rows = []
    for data in list_of_data:
        if not data:
            continue
        nfe = (data.get("nfe") or [{}])[0]
        totais = (data.get("totais") or [{}])[0]
        protocolo = (data.get("protocolo") or [{}])[0]
        nfe_rows.append({**nfe, **totais, **protocolo})

    # ---- Aba Itens: agregar todos os itens ----
    itens_rows = []
    for data in list_of_data:
        if data:
            itens_rows.extend(data.get("itens", []))

    # ---- Aba Financeiro: duplicatas + pagamento (coluna tipo) ----
    financeiro_rows = []
    for data in list_of_data:
        if not data:
            continue
        for dup in data.get("duplicatas", []):
            financeiro_rows.append({"tipo": "Duplicata", **dup})
        for pag in data.get("pagamento", []):
            financeiro_rows.append({"tipo": "Pagamento", **pag})

    # ---- Aba Transporte ----
    transporte_rows = []
    for data in list_of_data:
        if data:
            transporte_rows.extend(data.get("transporte", []))

    # ---- Aba Referencias ----
    referencias_rows = []
    for data in list_of_data:
        if data:
            referencias_rows.extend(data.get("referencias", []))

    sheets = {
        "NFe": nfe_rows,
        "Itens": itens_rows,
        "Financeiro": financeiro_rows,
        "Transporte": transporte_rows,
        "Referencias": referencias_rows,
    }

    with pd.ExcelWriter(output_path, engine=engine) as writer:
        for sheet_name, rows in sheets.items():
            if not rows:
                if sheet_name == "NFe":
                    pd.DataFrame(columns=["chave_NF"]).to_excel(writer, sheet_name=sheet_name, index=False)
                elif sheet_name == "Itens":
                    pd.DataFrame(columns=["chave_NF", "nItem"]).to_excel(writer, sheet_name=sheet_name, index=False)
                elif sheet_name == "Financeiro":
                    pd.DataFrame(columns=["chave_NF", "tipo"]).to_excel(writer, sheet_name=sheet_name, index=False)
                else:
                    pd.DataFrame(columns=["chave_NF"]).to_excel(writer, sheet_name=sheet_name, index=False)
                continue
            df = pd.DataFrame(rows)
            df = _normalize_columns(df)
            if sheet_name == "Itens":
                df = df[_column_order(list(df.columns), ["chave_NF", "nItem"])]
            elif sheet_name == "Financeiro":
                df = df[_column_order(list(df.columns), ["chave_NF", "tipo"])]
            else:
                df = df[_column_order(list(df.columns), ["chave_NF"])]
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    return output_path

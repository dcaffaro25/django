# -*- coding: utf-8 -*-
"""
Script para processar todos os XMLs de NFe em uma pasta e gerar um arquivo Excel
com abas separadas (NFe, Itens, Transporte, Duplicatas, Pagamento, Referências, Protocolo).
Os itens ficam vinculados à NF pela coluna chave_NF (e nItem na aba Itens).

Uso:
  python scripts/run_nfe_to_excel.py "C:/pasta/com/xmls" [--output saida.xlsx]
  python -m scripts.run_nfe_to_excel "C:/pasta/com/xmls"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Permitir import do engine a partir da raiz do projeto
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from scripts.nfe_engine.parser import parse_nfe_file
from scripts.nfe_engine.excel_export import export_to_excel


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Processa XMLs de NFe em uma pasta e gera um Excel com abas por entidade (NFe, Itens, etc.)."
    )
    parser.add_argument(
        "pasta",
        type=str,
        help="Pasta contendo os arquivos XML de NFe (procNFe ou NFe).",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Caminho do arquivo Excel de saída. Padrão: <pasta>/NFe_consolidado.xlsx",
    )
    parser.add_argument(
        "--glob",
        type=str,
        default="*.xml",
        help="Padrão de arquivos (default: *.xml). Ex.: *-procNFe.xml",
    )
    args = parser.parse_args()

    pasta = Path(args.pasta)
    if not pasta.is_dir():
        print(f"Erro: pasta não encontrada: {pasta}", file=sys.stderr)
        return 1

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = pasta / "NFe_consolidado.xlsx"

    arquivos = sorted(pasta.glob(args.glob))
    if not arquivos:
        print(f"Nenhum arquivo encontrado em {pasta} com padrão {args.glob}", file=sys.stderr)
        return 1

    list_of_data = []
    erros = []
    for arq in arquivos:
        try:
            data = parse_nfe_file(arq)
            if data is None:
                erros.append((str(arq), "Não é um XML de NFe válido ou não foi possível fazer parse"))
            else:
                list_of_data.append(data)
        except Exception as e:
            erros.append((str(arq), str(e)))

    if erros:
        for arq, msg in erros:
            print(f"Aviso: {arq} -> {msg}", file=sys.stderr)

    if not list_of_data:
        print("Nenhuma NFe válida para exportar.", file=sys.stderr)
        return 1

    out = export_to_excel(list_of_data, output_path)
    print(f"Exportado: {len(list_of_data)} NFe(s) -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

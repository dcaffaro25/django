# -*- coding: utf-8 -*-
"""
Importação de XMLs de evento NFe (cancelamento, CCe, manifestação) e de inutilização (ProcInutNFe).
Identifica automaticamente o tipo do XML (evento vs inutilização) e processa no fluxo correto.
"""
from django.db import transaction

from scripts.nfe_engine import detect_nfe_document_type, parse_nfe_evento_xml, parse_nfe_inut_xml

from billing.models import NotaFiscal, NFeEvento, NFeInutilizacao


def import_event_one(content, company, filename=""):
    """
    Importa um único XML de evento ou inutilização.
    Detecta o tipo automaticamente. Retorna:
      ("importado", evento), ("importado_inut", inut), ("duplicado", chave), ("erro", mensagem).
    """
    raw = content if isinstance(content, bytes) else content.encode("utf-8")
    doc_type = detect_nfe_document_type(raw)
    if doc_type == "nfe":
        return "erro", "Use o import de NFe para este arquivo (é uma nota fiscal, não evento)."
    if doc_type == "inutilizacao":
        return _import_inut_one(content, company, filename)
    if doc_type != "evento":
        return "erro", "Tipo de XML não reconhecido (esperado evento ou inutilização NFe)."

    data = parse_nfe_evento_xml(content, source_path=filename)
    if not data:
        return "erro", "XML inválido ou não é evento NFe"

    chave_nfe = data.get("chave_nfe", "").strip()
    if len(chave_nfe) != 44:
        return "erro", "Chave da NFe inválida ou ausente"

    tipo_evento = data.get("tipo_evento") or 0
    n_seq = data.get("n_seq_evento") or 1
    if NFeEvento.objects.filter(
        company=company,
        chave_nfe=chave_nfe,
        tipo_evento=tipo_evento,
        n_seq_evento=n_seq,
    ).exists():
        return "duplicado", chave_nfe

    with transaction.atomic():
        nota_fiscal = NotaFiscal.objects.filter(company=company, chave=chave_nfe).first()
        evento = NFeEvento.objects.create(
            company=company,
            chave_nfe=chave_nfe,
            tipo_evento=tipo_evento,
            n_seq_evento=n_seq,
            data_evento=data.get("data_evento"),
            descricao=data.get("descricao") or "",
            protocolo=data.get("protocolo") or "",
            status_sefaz=data.get("status_sefaz") or "",
            motivo_sefaz=data.get("motivo_sefaz") or "",
            data_registro=data.get("data_registro"),
            xml_original=data.get("xml_original") or "",
            arquivo_origem=data.get("arquivo_origem") or "",
            nota_fiscal=nota_fiscal,
        )
        if tipo_evento == 110111 and nota_fiscal:
            nota_fiscal.status_sefaz = data.get("status_sefaz") or "101"
            nota_fiscal.motivo_sefaz = (data.get("motivo_sefaz") or "")[:300]
            nota_fiscal.save(update_fields=["status_sefaz", "motivo_sefaz", "updated_at"])
    return "importado", evento


def _import_inut_one(content, company, filename=""):
    """Importa um XML ProcInutNFe. Retorna ("importado_inut", inut), ("duplicado", key) ou ("erro", msg)."""
    data = parse_nfe_inut_xml(content, source_path=filename)
    if not data:
        return "erro", "XML inválido ou não é inutilização NFe (ProcInutNFe)."

    ano = data.get("ano", "").strip()
    serie = data.get("serie", 1)
    n_ini = data.get("n_nf_ini", 0)
    n_fin = data.get("n_nf_fin", 0)
    if not ano or n_ini <= 0 or n_fin < n_ini:
        return "erro", "Dados da inutilização inválidos (ano/série/números)."

    if NFeInutilizacao.objects.filter(
        company=company, ano=ano, serie=serie, n_nf_ini=n_ini, n_nf_fin=n_fin
    ).exists():
        return "duplicado", f"Inut {ano}/S{serie} {n_ini}-{n_fin}"

    with transaction.atomic():
        inut = NFeInutilizacao.objects.create(
            company=company,
            cuf=data.get("cuf") or "",
            ano=ano,
            cnpj=data.get("cnpj") or "",
            modelo=data.get("modelo") or 55,
            serie=serie,
            n_nf_ini=n_ini,
            n_nf_fin=n_fin,
            x_just=data.get("x_just") or "",
            protocolo=data.get("protocolo") or "",
            status_sefaz=data.get("status_sefaz") or "",
            motivo_sefaz=data.get("motivo_sefaz") or "",
            data_registro=data.get("data_registro"),
            xml_original=data.get("xml_original") or "",
            arquivo_origem=data.get("arquivo_origem") or "",
        )
    return "importado_inut", inut


def import_events_many(files, company):
    """
    files: lista de arquivos (com .read() e .name) ou de (filename, content).
    company: Company (tenant).
    Detecta automaticamente evento vs inutilização por XML.
    Retorna: {"importados": [...], "importados_inut": [...], "duplicados": [...], "erros": [...]}
    """
    importados = []
    importados_inut = []
    duplicados = []
    erros = []

    for f in files:
        if hasattr(f, "read") and hasattr(f, "name"):
            filename = getattr(f, "name", "") or ""
            try:
                content = f.read()
                if isinstance(content, bytes):
                    content = content.decode("utf-8", errors="replace")
            except Exception as e:
                erros.append({"arquivo": filename, "erro": str(e)})
                continue
        else:
            filename, content = f[0], f[1]
            if isinstance(content, bytes):
                content = content.decode("utf-8", errors="replace")

        status, payload = import_event_one(content, company, filename)
        if status == "importado":
            importados.append({
                "chave_nfe": payload.chave_nfe,
                "id": payload.pk,
                "tipo_evento": payload.tipo_evento,
                "n_seq_evento": payload.n_seq_evento,
            })
        elif status == "importado_inut":
            importados_inut.append({
                "ano": payload.ano,
                "serie": payload.serie,
                "n_nf_ini": payload.n_nf_ini,
                "n_nf_fin": payload.n_nf_fin,
                "id": payload.pk,
            })
        elif status == "duplicado":
            duplicados.append(payload)
        else:
            erros.append({"arquivo": filename, "erro": payload})

    return {
        "importados": importados,
        "importados_inut": importados_inut,
        "duplicados": duplicados,
        "erros": erros,
    }

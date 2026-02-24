# -*- coding: utf-8 -*-
"""
Engine de importação de NFe: recebe XML(s), usa o parser e persiste em NotaFiscal/NotaFiscalItem.
Suporta múltiplos arquivos; trata duplicatas por chave; resolve FKs (emitente, destinatário, produto).
Antes de criar parceiros ou produtos, aplica SubstitutionRule (de-para) para resolver por identificador/código.
"""
import re
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from datetime import datetime

from django.db import transaction

from scripts.nfe_engine.parser import parse_nfe_xml
from scripts.nfe_engine import detect_nfe_document_type
from multitenancy.models import SubstitutionRule

from billing.services.nfe_event_import_service import import_event_one
from billing.models import (
    NotaFiscal,
    NotaFiscalItem,
    NotaFiscalReferencia,
    BusinessPartner,
    ProductService,
)


def _safe_int(val, default=0):
    if val is None or val == "":
        return default
    try:
        return int(Decimal(str(val).strip().split(".")[0]))
    except (ValueError, InvalidOperation):
        return default


def _safe_decimal(val, default=Decimal("0")):
    if val is None or val == "":
        return default
    try:
        return Decimal(str(val).strip().replace(",", "."))
    except (ValueError, InvalidOperation):
        return default


def _decimal_to_field(val, max_digits, decimal_places, default=Decimal("0")):
    """
    Converte valor para Decimal, trunca às casas decimais permitidas e limita ao
    intervalo que cabe no campo (evita overflow em numeric(max_digits, decimal_places)).
    """
    d = _safe_decimal(val, default)
    max_int_digits = max_digits - decimal_places
    max_abs = (Decimal(10) ** max_int_digits) - (Decimal(10) ** -decimal_places)
    if d > max_abs:
        d = max_abs
    elif d < -max_abs:
        d = -max_abs
    quantize_exp = Decimal(10) ** -decimal_places
    return d.quantize(quantize_exp, rounding=ROUND_DOWN)


def _safe_date(val):
    if not val or not str(val).strip():
        return None
    s = str(val).strip()
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _build_transporte_json(transporte_rows, mod_frete_val):
    """Monta transporte_json a partir da lista de linhas do parser."""
    if not transporte_rows:
        return {"modFrete": str(mod_frete_val), "transportadora": {}, "volumes": []}
    first = transporte_rows[0]
    transportadora = {}
    if first.get("transporta_CNPJ"):
        transportadora["CNPJ"] = first["transporta_CNPJ"]
    if first.get("transporta_xNome"):
        transportadora["xNome"] = first["transporta_xNome"]
    if first.get("transporta_UF"):
        transportadora["UF"] = first["transporta_UF"]
    volumes = []
    for row in transporte_rows:
        vol = {}
        for k, v in row.items():
            if k.startswith("vol_") and v:
                vol[k.replace("vol_", "")] = v
        if vol:
            volumes.append(vol)
    return {
        "modFrete": str(mod_frete_val),
        "transportadora": transportadora,
        "volumes": volumes,
    }


def _build_financeiro_json(duplicatas, pagamento):
    """Lista única com tipo duplicata | pagamento."""
    out = []
    for d in duplicatas:
        out.append({
            "tipo": "duplicata",
            "nDup": d.get("nDup", ""),
            "dVenc": d.get("dVenc", ""),
            "vDup": d.get("vDup", ""),
        })
    for p in pagamento:
        out.append({
            "tipo": "pagamento",
            "indPag": p.get("indPag", ""),
            "tPag": p.get("tPag", ""),
            "vPag": p.get("vPag", ""),
        })
    return out


def _build_referencias_json(referencias):
    """Lista de chaves (refNFe) ou refNF como string identificadora."""
    out = []
    for r in referencias:
        if r.get("refNFe"):
            out.append(r["refNFe"])
        elif r.get("refNF_CNPJ") or r.get("refNF_nNF"):
            out.append({
                "refNF_CNPJ": r.get("refNF_CNPJ", ""),
                "refNF_nNF": r.get("refNF_nNF", ""),
                "refNF_serie": r.get("refNF_serie", ""),
            })
    return out


def _apply_substitution_rule(company, model_name, field_name, incoming_value):
    """
    Aplica regras de substituição (SubstitutionRule) para um valor de um dado modelo/campo.
    Retorna o valor substituído se alguma regra fizer match; caso contrário retorna None.
    """
    if incoming_value is None or (isinstance(incoming_value, str) and not incoming_value.strip()):
        return None
    incoming_str = str(incoming_value).strip()
    rules = SubstitutionRule.objects.filter(
        company=company, model_name=model_name, field_name=field_name
    )
    for rule in rules:
        match_val = (rule.match_value or "").strip()
        subst_val = (rule.substitution_value or "").strip()
        if rule.match_type == "exact":
            if match_val == incoming_str:
                return subst_val if subst_val else None
        elif rule.match_type == "caseless":
            if match_val.lower() == incoming_str.lower():
                return subst_val if subst_val else None
        elif rule.match_type == "regex":
            try:
                if re.search(rule.match_value, incoming_str):
                    return re.sub(rule.match_value, rule.substitution_value, incoming_str).strip() or None
            except re.error:
                continue
    return None


def _resolve_emitente(company, emit_cnpj, emit_nome="", emit_fantasia="", emit_uf="", emit_municipio=""):
    """Retorna BusinessPartner: 1) direto por identifier, 2) via SubstitutionRule (de-para), 3) cria novo."""
    if not emit_cnpj or not company:
        return None
    cnpj_clean = "".join(c for c in str(emit_cnpj) if c.isdigit())[:50]
    if not cnpj_clean:
        return None
    qs = BusinessPartner.objects.filter(company=company)
    bp = qs.filter(identifier=emit_cnpj).first() or qs.filter(identifier=cnpj_clean).first()
    if bp:
        return bp
    substituted = _apply_substitution_rule(company, "BusinessPartner", "identifier", cnpj_clean)
    if not substituted:
        substituted = _apply_substitution_rule(company, "BusinessPartner", "identifier", emit_cnpj)
    if substituted:
        bp = qs.filter(identifier=substituted).first()
        if bp:
            return bp
    name = (emit_nome or emit_fantasia or cnpj_clean).strip()[:255] or cnpj_clean
    try:
        bp = BusinessPartner.objects.create(
            company=company,
            identifier=cnpj_clean,
            name=name,
            partner_type="both",
            state=emit_uf[:100] if emit_uf else "",
            city=emit_municipio[:100] if emit_municipio else "",
            category=None,
            currency=None,
        )
        return bp
    except Exception:
        return None


def _resolve_destinatario(company, dest_cnpj, dest_nome="", dest_uf=""):
    """Retorna BusinessPartner: 1) direto por identifier, 2) via SubstitutionRule (de-para), 3) cria novo."""
    if not dest_cnpj or not company:
        return None
    cnpj_clean = "".join(c for c in str(dest_cnpj) if c.isdigit())[:50]
    if not cnpj_clean:
        return None
    qs = BusinessPartner.objects.filter(company=company)
    bp = qs.filter(identifier=dest_cnpj).first() or qs.filter(identifier=cnpj_clean).first()
    if bp:
        return bp
    substituted = _apply_substitution_rule(company, "BusinessPartner", "identifier", cnpj_clean)
    if not substituted:
        substituted = _apply_substitution_rule(company, "BusinessPartner", "identifier", dest_cnpj)
    if substituted:
        bp = qs.filter(identifier=substituted).first()
        if bp:
            return bp
    name = (dest_nome or cnpj_clean).strip()[:255] or cnpj_clean
    try:
        bp = BusinessPartner.objects.create(
            company=company,
            identifier=cnpj_clean,
            name=name,
            partner_type="both",
            state=dest_uf[:100] if dest_uf else "",
            city="",
            category=None,
            currency=None,
        )
        return bp
    except Exception:
        return None


def _resolve_produto(company, codigo_produto, ean, descricao="", valor_unitario=None):
    """
    Retorna ProductService: 1) direto por code/EAN, 2) via SubstitutionRule (ProductService.code),
    3) cria novo com dados do item da NFe.
    """
    if not company:
        return None
    qs = ProductService.objects.filter(company=company)
    for code_candidate in (codigo_produto, ean):
        if not code_candidate:
            continue
        p = qs.filter(code=code_candidate).first()
        if p:
            return p
    for code_candidate in (codigo_produto, ean):
        if not code_candidate:
            continue
        substituted = _apply_substitution_rule(company, "ProductService", "code", code_candidate)
        if substituted:
            p = qs.filter(code=substituted).first()
            if p:
                return p
    code_final = (codigo_produto or ean or "").strip()[:100]
    if not code_final:
        return None
    name = (descricao or code_final).strip()[:255] or code_final
    price = valor_unitario if valor_unitario is not None else Decimal("0")
    try:
        p = ProductService.objects.create(
            company=company,
            code=code_final,
            name=name,
            item_type="product",
            price=price,
            cost=valor_unitario,
            category=None,
            currency=None,
        )
        return p
    except Exception:
        return None


def _map_parser_to_notafiscal(data, company, xml_content, arquivo_origem):
    """Mapeia resultado do parser para um único NotaFiscal + itens. Retorna (nf, None) ou (None, error_msg)."""
    nfe_row = (data.get("nfe") or [{}])[0]
    totais = (data.get("totais") or [{}])[0]
    protocolo = (data.get("protocolo") or [{}])[0]
    chave = (nfe_row.get("chave_NF") or "").strip()
    if not chave or len(chave) != 44:
        return None, "Chave inválida ou ausente"

    if NotaFiscal.objects.filter(chave=chave).exists():
        return "duplicada", None  # signal para não inserir, apenas reportar

    # ide_*
    ide = nfe_row
    numero = _safe_int(ide.get("ide_nNF"))
    serie = _safe_int(ide.get("ide_serie"), 1)
    modelo = _safe_int(ide.get("ide_mod"), 55)
    tipo_operacao = _safe_int(ide.get("ide_tpNF"), 0)
    finalidade = _safe_int(ide.get("ide_finNFe"), 1)
    natureza_operacao = (ide.get("ide_natOp") or "")[:200]
    ambiente = _safe_int(ide.get("ide_tpAmb"), 1)
    id_destino = _safe_int(ide.get("ide_idDest"), 1)
    ind_final = _safe_int(ide.get("ide_indFinal"), 0)
    ind_presenca = _safe_int(ide.get("ide_indPres"), 9)
    data_emissao = _safe_date(ide.get("ide_dhEmi"))
    data_saida_entrada = _safe_date(ide.get("ide_dhSaiEnt"))
    if not data_emissao:
        return None, "Data de emissão ausente"

    # Emitente
    emit_cnpj = (ide.get("emit_CNPJ") or "").strip()[:14]
    emit_nome = (ide.get("emit_xNome") or "").strip()[:300]
    emit_fantasia = (ide.get("emit_xFant") or "").strip()[:300]
    emit_uf = (ide.get("emit_UF") or "").strip()[:2]
    emit_municipio = (ide.get("emit_xMun") or "").strip()[:100]
    emit_ie = (ide.get("emit_IE") or "")[:20]
    emit_crt = (ide.get("emit_CRT") or "")[:1]

    # Destinatário
    dest_cnpj = (ide.get("dest_CNPJ") or "").strip()[:14]
    dest_nome = (ide.get("dest_xNome") or "").strip()[:300]
    dest_ie = (ide.get("dest_IE") or "")[:20]
    dest_uf = (ide.get("dest_UF") or "").strip()[:2]
    dest_ind_ie = (ide.get("dest_indIEDest") or "")[:1]

    # Totais (15,2) — truncar/limitar para evitar overflow
    def _d15_2(v):
        return _decimal_to_field(v, 15, 2)
    valor_nota = _d15_2(ide.get("vNF"))
    valor_produtos = _d15_2(ide.get("vProd"))
    valor_icms = _d15_2(ide.get("vICMS"))
    valor_icms_st = _d15_2(totais.get("tot_vST") or ide.get("vST"))
    valor_ipi = _d15_2(totais.get("tot_vIPI") or ide.get("vIPI"))
    valor_pis = _d15_2(ide.get("vPIS"))
    valor_cofins = _d15_2(ide.get("vCOFINS"))
    valor_frete = _d15_2(ide.get("vFrete"))
    valor_seguro = _d15_2(totais.get("tot_vSeg"))
    valor_desconto = _d15_2(ide.get("vDesc"))
    valor_outras = _d15_2(totais.get("tot_vOutro"))
    valor_icms_uf_dest = _d15_2(totais.get("tot_vICMSUFDest"))
    valor_trib_aprox = _d15_2(totais.get("tot_vTotTrib"))

    # Protocolo
    protocolo_str = (protocolo.get("nProt") or "").strip()[:20]
    status_sefaz = (protocolo.get("cStat") or "").strip()[:5]
    motivo_sefaz = (protocolo.get("xMotivo") or "").strip()[:300]
    data_autorizacao = _safe_date(protocolo.get("dhRecbto"))

    # Transporte (modFrete vem da primeira linha de transporte)
    mod_frete = _safe_int((data.get("transporte") or [{}])[0].get("modFrete"), 9)
    transporte_json = _build_transporte_json(data.get("transporte") or [], mod_frete)
    financeiro_json = _build_financeiro_json(data.get("duplicatas") or [], data.get("pagamento") or [])
    referencias_json = _build_referencias_json(data.get("referencias") or [])
    totais_json = {k.replace("tot_", ""): v for k, v in totais.items() if k.startswith("tot_") and v not in (None, "")}

    info_complementar = (ide.get("infCpl") or "")[:5000]
    info_fisco = (ide.get("infAdFisco") or "")[:5000]
    xml_original = (xml_content or "")  # store full XML (TextField has no practical limit)
    arquivo_origem_str = (arquivo_origem or "")[:500]

    emitente = _resolve_emitente(
        company, emit_cnpj,
        emit_nome=emit_nome, emit_fantasia=emit_fantasia,
        emit_uf=emit_uf, emit_municipio=emit_municipio,
    )
    destinatario = _resolve_destinatario(
        company, dest_cnpj,
        dest_nome=dest_nome, dest_uf=dest_uf,
    )

    nf = NotaFiscal(
        company=company,
        chave=chave,
        numero=numero,
        serie=serie,
        modelo=modelo,
        tipo_operacao=tipo_operacao,
        finalidade=finalidade,
        natureza_operacao=natureza_operacao,
        ambiente=ambiente,
        id_destino=id_destino,
        ind_final=ind_final,
        ind_presenca=ind_presenca,
        data_emissao=data_emissao,
        data_saida_entrada=data_saida_entrada,
        emit_cnpj=emit_cnpj,
        emit_nome=emit_nome,
        emit_fantasia=emit_fantasia,
        emit_ie=emit_ie,
        emit_crt=emit_crt,
        emit_uf=emit_uf,
        emit_municipio=emit_municipio,
        emitente=emitente,
        dest_cnpj=dest_cnpj,
        dest_nome=dest_nome,
        dest_ie=dest_ie,
        dest_uf=dest_uf,
        dest_ind_ie=dest_ind_ie,
        destinatario=destinatario,
        valor_nota=valor_nota,
        valor_produtos=valor_produtos,
        valor_icms=valor_icms,
        valor_icms_st=valor_icms_st,
        valor_ipi=valor_ipi,
        valor_pis=valor_pis,
        valor_cofins=valor_cofins,
        valor_frete=valor_frete,
        valor_seguro=valor_seguro,
        valor_desconto=valor_desconto,
        valor_outras=valor_outras,
        valor_icms_uf_dest=valor_icms_uf_dest,
        valor_trib_aprox=valor_trib_aprox,
        protocolo=protocolo_str,
        status_sefaz=status_sefaz,
        motivo_sefaz=motivo_sefaz,
        data_autorizacao=data_autorizacao,
        mod_frete=mod_frete,
        transporte_json=transporte_json,
        financeiro_json=financeiro_json,
        referencias_json=referencias_json,
        totais_json=totais_json,
        info_complementar=info_complementar,
        info_fisco=info_fisco,
        xml_original=xml_original,
        arquivo_origem=arquivo_origem_str,
    )
    return nf, None


def _map_item_to_model(item_data, nota_fiscal, company):
    """Cria instância NotaFiscalItem a partir de um dict do parser (prefixos prod_, ICMS_, etc.)."""
    n_item = _safe_int(item_data.get("nItem"), 1)
    prod = item_data
    codigo_produto = (prod.get("prod_cProd") or "").strip()[:60]
    ean = (prod.get("prod_cEAN") or "").strip()[:14]
    descricao = (prod.get("prod_xProd") or "").strip()[:500]
    ncm = (prod.get("prod_NCM") or "").strip()[:8]
    cest = (prod.get("prod_CEST") or "").strip()[:7]
    cfop = (prod.get("prod_CFOP") or "").strip()[:4]
    unidade = (prod.get("prod_uCom") or "UN").strip()[:6]
    # Truncar/limitar decimais ao tamanho do campo para evitar overflow
    quantidade = _decimal_to_field(prod.get("prod_qCom"), 15, 4)
    valor_unitario = _decimal_to_field(prod.get("prod_vUnCom"), 18, 10)
    valor_total = _decimal_to_field(prod.get("prod_vProd"), 15, 2)
    info_adicional = (prod.get("infAdProd") or "")[:2000]

    icms_origem = _safe_int(prod.get("ICMS_orig"), 0)
    icms_cst = (prod.get("ICMS_CST") or "").strip()[:4]
    icms_base = _decimal_to_field(prod.get("ICMS_vBC"), 15, 2)
    icms_aliquota = _decimal_to_field(prod.get("ICMS_pICMS"), 7, 4)
    icms_valor = _decimal_to_field(prod.get("ICMS_vICMS"), 15, 2)
    icms_st_base = _decimal_to_field(prod.get("ICMS_vBCST"), 15, 2)
    icms_st_valor = _decimal_to_field(prod.get("ICMS_vICMSST"), 15, 2)

    pis_cst = (prod.get("PIS_CST") or "").strip()[:2]
    pis_base = _decimal_to_field(prod.get("PIS_vBC"), 15, 2)
    pis_aliquota = _decimal_to_field(prod.get("PIS_pPIS"), 7, 4)
    pis_valor = _decimal_to_field(prod.get("PIS_vPIS"), 15, 2)

    cofins_cst = (prod.get("COFINS_CST") or "").strip()[:2]
    cofins_base = _decimal_to_field(prod.get("COFINS_vBC"), 15, 2)
    cofins_aliquota = _decimal_to_field(prod.get("COFINS_pCOFINS"), 7, 4)
    cofins_valor = _decimal_to_field(prod.get("COFINS_vCOFINS"), 15, 2)

    ipi_cst = (prod.get("IPI_CST") or "").strip()[:2]
    ipi_valor = _decimal_to_field(prod.get("IPI_vIPI"), 15, 2)

    icms_uf_dest_base = _decimal_to_field(prod.get("vBCUFDest"), 15, 2)
    icms_uf_dest_valor = _decimal_to_field(prod.get("vICMSUFDest"), 15, 2)
    icms_uf_remet_valor = Decimal("0")  # parser pode não expor; manter 0

    # Impostos completos: guardar dict com as chaves que vieram do parser para o item
    impostos_json = {}
    for k, v in prod.items():
        if k.startswith("ICMS_") or k.startswith("PIS_") or k.startswith("COFINS_") or k in ("vBCUFDest", "vICMSUFDest", "vTotTrib"):
            if v not in (None, ""):
                impostos_json[k] = v

    produto = _resolve_produto(
        company, codigo_produto, ean,
        descricao=descricao, valor_unitario=valor_unitario,
    )

    return NotaFiscalItem(
        nota_fiscal=nota_fiscal,
        company=company,
        numero_item=n_item,
        codigo_produto=codigo_produto or "0",
        ean=ean,
        descricao=descricao or "-",
        ncm=ncm or "0",
        cest=cest,
        cfop=cfop or "0",
        unidade=unidade,
        quantidade=quantidade,
        valor_unitario=valor_unitario,
        valor_total=valor_total,
        produto=produto,
        icms_origem=icms_origem,
        icms_cst=icms_cst,
        icms_base=icms_base,
        icms_aliquota=icms_aliquota,
        icms_valor=icms_valor,
        icms_st_base=icms_st_base,
        icms_st_valor=icms_st_valor,
        pis_cst=pis_cst,
        pis_base=pis_base,
        pis_aliquota=pis_aliquota,
        pis_valor=pis_valor,
        cofins_cst=cofins_cst,
        cofins_base=cofins_base,
        cofins_aliquota=cofins_aliquota,
        cofins_valor=cofins_valor,
        ipi_cst=ipi_cst,
        ipi_valor=ipi_valor,
        icms_uf_dest_base=icms_uf_dest_base,
        icms_uf_dest_valor=icms_uf_dest_valor,
        icms_uf_remet_valor=icms_uf_remet_valor,
        impostos_json=impostos_json,
        info_adicional=info_adicional,
    )


def import_one(xml_content, company, filename=""):
    """
    Importa um único XML. Retorna:
    - ("importada", nf) em sucesso
    - ("duplicada", chave) se a chave já existir
    - ("erro", mensagem) em falha de parse ou validação
    """
    data = parse_nfe_xml(xml_content, source_path=filename)
    if not data:
        raw = xml_content if isinstance(xml_content, bytes) else xml_content.encode("utf-8")
        doc_type = detect_nfe_document_type(raw)
        if doc_type == "evento":
            return "erro", "Este arquivo é um evento NFe (cancelamento, CCe, etc.). Use o import de EVENTOS (não o de NFe)."
        if doc_type == "inutilizacao":
            return "erro", "Este arquivo é uma inutilização de numeração (ProcInutNFe). Use o import de EVENTOS (não o de NFe)."
        return "erro", "XML inválido ou não é NFe"

    nf_or_signal, err = _map_parser_to_notafiscal(data, company, xml_content, filename)
    if err:
        return "erro", err
    if nf_or_signal == "duplicada":
        chave = (data.get("nfe") or [{}])[0].get("chave_NF", "")
        return "duplicada", chave

    nf = nf_or_signal
    with transaction.atomic():
        nf.save()
        for item_data in data.get("itens") or []:
            item = _map_item_to_model(item_data, nf, company)
            item.save()
        # Vincular referências: criar NotaFiscalReferencia para cada refNFe (chave 44)
        # e preencher nota_referenciada quando a NF referenciada já existir
        for ref in nf.referencias_json or []:
            chave_ref = None
            if isinstance(ref, str) and len(ref.strip()) == 44:
                chave_ref = ref.strip()
            elif isinstance(ref, dict) and ref.get("refNFe") and len(str(ref["refNFe"]).strip()) == 44:
                chave_ref = str(ref["refNFe"]).strip()
            if not chave_ref:
                continue
            if NotaFiscalReferencia.objects.filter(
                company=company, nota_fiscal=nf, chave_referenciada=chave_ref
            ).exists():
                continue
            nota_ref = NotaFiscal.objects.filter(company=company, chave=chave_ref).first()
            NotaFiscalReferencia.objects.create(
                company=company,
                nota_fiscal=nf,
                chave_referenciada=chave_ref,
                nota_referenciada=nota_ref,
            )
        # Preencher vínculos reversos: NFs que referenciam ESTA NF (por chave) e ainda
        # tinham nota_referenciada=None passam a apontar para esta NF
        NotaFiscalReferencia.objects.filter(
            company=company,
            chave_referenciada=nf.chave,
            nota_referenciada__isnull=True,
        ).update(nota_referenciada=nf)
    return "importada", nf


def import_many(files, company):
    """
    files: lista de (filename, content) ou lista de arquivos tipo UploadedFile com .read() e .name.
    company: instância Company (tenant).
    Retorna: {"importadas": [{"chave": ..., "id": ...}], "duplicadas": [chave, ...], "erros": [{"arquivo": ..., "erro": ...}]}
    """
    importadas = []
    duplicadas = []
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

        status, payload = import_one(content, company, filename)
        if status == "importada":
            importadas.append({"chave": payload.chave, "id": payload.pk, "numero": payload.numero})
        elif status == "duplicada":
            duplicadas.append(payload)
        else:
            erros.append({"arquivo": filename, "erro": payload})

    return {
        "importadas": importadas,
        "duplicadas": duplicadas,
        "erros": erros,
    }


def _should_auto_ingest(company):
    """Check if this tenant has auto-ingestion enabled."""
    from inventory.models_costing import TenantCostingConfig
    config = TenantCostingConfig.objects.filter(company=company).first()
    return config is not None and getattr(config, "auto_ingest_on_nfe_import", False)


def _schedule_inventory_ingest(company_id, nota_fiscal_ids):
    """Fire the Celery task to ingest NF movements."""
    from inventory.tasks import ingest_nf_movements_task
    ingest_nf_movements_task.delay(company_id, nota_fiscal_ids=nota_fiscal_ids)


def import_nfe_xml_many(files, company):
    """
    Um único ponto de importação: para cada XML detecta o tipo (NFe, evento ou inutilização)
    e processa com o importador correto.
    Atômico: toda a operação roda em uma transação; se qualquer arquivo falhar,
    nada é commitado (rollback completo).
    Retorna: importadas (NFe), importados (eventos), importados_inut (inutilizações),
             duplicadas (chaves/identificadores), erros.
    """
    importadas = []
    importados = []
    importados_inut = []
    duplicadas = []
    erros = []

    with transaction.atomic():
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

            raw = content if isinstance(content, bytes) else content.encode("utf-8")
            doc_type = detect_nfe_document_type(raw)

            if doc_type == "nfe":
                status, payload = import_one(content, company, filename)
                if status == "importada":
                    importadas.append({"chave": payload.chave, "id": payload.pk, "numero": payload.numero})
                elif status == "duplicada":
                    duplicadas.append(payload)
                else:
                    erros.append({"arquivo": filename, "erro": payload})
            elif doc_type in ("evento", "inutilizacao"):
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
                    duplicadas.append(payload)
                else:
                    erros.append({"arquivo": filename, "erro": payload})
            else:
                erros.append({
                    "arquivo": filename,
                    "erro": "Tipo de XML não reconhecido (esperado NFe, evento ou inutilização).",
                })

        if erros:
            transaction.set_rollback(True)
            importadas = []
            importados = []
            importados_inut = []

        nf_ids = [nf["id"] for nf in importadas]
        if nf_ids and _should_auto_ingest(company):
            transaction.on_commit(
                lambda ids=nf_ids, cid=company.id: _schedule_inventory_ingest(cid, ids)
            )
            inventory_triggered = True
        else:
            inventory_triggered = False

    return {
        "importadas": importadas,
        "importados": importados,
        "importados_inut": importados_inut,
        "duplicadas": duplicadas,
        "erros": erros,
        "inventory_triggered": inventory_triggered,
    }

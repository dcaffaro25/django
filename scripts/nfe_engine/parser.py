# -*- coding: utf-8 -*-
"""
Parser de XML NFe (Nota Fiscal Eletrônica) padrão brasileiro.
Extrai dados hierárquicos em estruturas tabulares, com chave da NF para vínculo.
"""
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Namespace padrão NFe (Portal da NF-e)
NS = {"nfe": "http://www.portalfiscal.inf.br/nfe"}


def _text(el: Optional[ET.Element], default: str = "") -> str:
    if el is not None and el.text is not None:
        return (el.text or "").strip()
    return default


def _get_chave(inf_nfe: ET.Element) -> str:
    """Obtém a chave da NFe (44 dígitos) do atributo Id de infNFe."""
    id_attr = inf_nfe.get("Id", "")
    if id_attr.startswith("NFe"):
        return id_attr[3:]  # remove prefixo "NFe"
    return id_attr


def _first_child(parent: Optional[ET.Element], *tags: str):
    """Retorna o primeiro filho que corresponda a uma das tags (com namespace)."""
    if parent is None:
        return None
    for tag in tags:
        for fmt in ("nfe:%s", "{http://www.portalfiscal.inf.br/nfe}%s"):
            if "{" in fmt:
                full_tag = fmt % tag
            else:
                full_tag = f"{{{NS['nfe']}}}{tag}" if fmt.startswith("nfe:") else fmt % tag
            child = parent.find(f".//{full_tag}")
            if child is not None:
                return child
    return None


def _flatten_imposto(imposto: Optional[ET.Element]) -> Dict[str, str]:
    """Extrai valores de impostos do item (ICMS*, PIS*, COFINS*, IPI, ICMSUFDest)."""
    out = {}
    if imposto is None:
        return out
    # ICMS - pode ser ICMS00, ICMS10, ICMS60, etc.
    for tag in ("ICMS00", "ICMS10", "ICMS20", "ICMS30", "ICMS40", "ICMS51", "ICMS60", "ICMS90", "ICMSSN101", "ICMSSN102", "ICMSSN900"):
        node = imposto.find(f".//nfe:{tag}", NS) or imposto.find(f".//{{{NS['nfe']}}}{tag}")
        if node is not None:
            for child in node:
                local_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                out[f"ICMS_{local_tag}"] = _text(child)
            out["ICMS_CST"] = _text(node.find(".//nfe:CST", NS) or node.find(f".//{{{NS['nfe']}}}CST"))
            break
    # PIS
    for tag in ("PISAliq", "PISOutr", "PISQtde", "PISNT", "PISN"):
        node = imposto.find(f".//nfe:{tag}", NS) or imposto.find(f".//{{{NS['nfe']}}}{tag}")
        if node is not None:
            out["PIS_vBC"] = _text(node.find(".//nfe:vBC", NS) or node.find(f".//{{{NS['nfe']}}}vBC"))
            out["PIS_pPIS"] = _text(node.find(".//nfe:pPIS", NS) or node.find(f".//{{{NS['nfe']}}}pPIS"))
            out["PIS_vPIS"] = _text(node.find(".//nfe:vPIS", NS) or node.find(f".//{{{NS['nfe']}}}vPIS"))
            out["PIS_CST"] = _text(node.find(".//nfe:CST", NS) or node.find(f".//{{{NS['nfe']}}}CST"))
            break
    # COFINS
    for tag in ("COFINSAliq", "COFINSOutr", "COFINSQtde", "COFINSNT", "COFINSN"):
        node = imposto.find(f".//nfe:{tag}", NS) or imposto.find(f".//{{{NS['nfe']}}}{tag}")
        if node is not None:
            out["COFINS_vBC"] = _text(node.find(".//nfe:vBC", NS) or node.find(f".//{{{NS['nfe']}}}vBC"))
            out["COFINS_pCOFINS"] = _text(node.find(".//nfe:pCOFINS", NS) or node.find(f".//{{{NS['nfe']}}}pCOFINS"))
            out["COFINS_vCOFINS"] = _text(node.find(".//nfe:vCOFINS", NS) or node.find(f".//{{{NS['nfe']}}}vCOFINS"))
            out["COFINS_CST"] = _text(node.find(".//nfe:CST", NS) or node.find(f".//{{{NS['nfe']}}}CST"))
            break
    # IPI (quando existir)
    ipi = imposto.find(".//nfe:IPITrib", NS) or imposto.find(f".//{{{NS['nfe']}}}IPITrib")
    if ipi is not None:
        out["IPI_vIPI"] = _text(ipi.find(".//nfe:vIPI", NS) or ipi.find(f".//{{{NS['nfe']}}}vIPI"))
    # ICMS UF Destino (interestadual)
    icms_uf = imposto.find(".//nfe:ICMSUFDest", NS) or imposto.find(f".//{{{NS['nfe']}}}ICMSUFDest")
    if icms_uf is not None:
        out["vICMSUFDest"] = _text(icms_uf.find(".//nfe:vICMSUFDest", NS) or icms_uf.find(f".//{{{NS['nfe']}}}vICMSUFDest"))
        out["vBCUFDest"] = _text(icms_uf.find(".//nfe:vBCUFDest", NS) or icms_uf.find(f".//{{{NS['nfe']}}}vBCUFDest"))
    # Tributo aproximado (item)
    v_tot_trib = imposto.find(".//nfe:vTotTrib", NS) or imposto.find(f".//{{{NS['nfe']}}}vTotTrib")
    if v_tot_trib is not None:
        out["vTotTrib"] = _text(v_tot_trib)
    return out


def _dict_from_children(parent: Optional[ET.Element], prefix: str = "") -> Dict[str, Any]:
    """Converte filhos diretos de parent em dict: prefix+nome_tag -> text."""
    out = {}
    if parent is None:
        return out
    for child in parent:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        key = f"{prefix}_{tag}" if prefix else tag
        out[key] = _text(child)
    return out


def parse_nfe_xml(content: Union[str, bytes], source_path: Optional[str] = None) -> Optional[Dict[str, List[dict]]]:
    """
    Parse de um XML de NFe (conteúdo string ou bytes).
    Retorna um dicionário com listas de linhas por aba:
      - nfe: cabeçalho (uma linha por NF)
      - itens: detalhes dos itens (chave_NF + nItem vinculam à NF)
      - totais: totais da NF (pode ser mesclado ao cabeçalho; mantido separado para compatibilidade)
      - transporte: dados de transporte
      - duplicatas: cobrança (dup)
      - pagamento: detPag
      - referencias: NFref
      - protocolo: infProt
    Se o XML não for NFe válido, retorna None.
    """
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return None
    # nfeProc ou NFe direto
    nfe_proc = root.find(".//nfe:nfeProc", NS) or root.find(f".//{{{NS['nfe']}}}nfeProc")
    if nfe_proc is None:
        inf_nfe = root.find(".//nfe:infNFe", NS) or root.find(f".//{{{NS['nfe']}}}infNFe")
        prot = root.find(".//nfe:protNFe", NS) or root.find(f".//{{{NS['nfe']}}}protNFe")
    else:
        inf_nfe = nfe_proc.find(".//nfe:infNFe", NS) or nfe_proc.find(f".//{{{NS['nfe']}}}infNFe")
        prot = nfe_proc.find(".//nfe:protNFe", NS) or nfe_proc.find(f".//{{{NS['nfe']}}}protNFe")
    if inf_nfe is None:
        return None

    chave = _get_chave(inf_nfe)
    ide = inf_nfe.find("nfe:ide", NS) or inf_nfe.find(f"{{{NS['nfe']}}}ide")
    emit = inf_nfe.find("nfe:emit", NS) or inf_nfe.find(f"{{{NS['nfe']}}}emit")
    dest = inf_nfe.find("nfe:dest", NS) or inf_nfe.find(f"{{{NS['nfe']}}}dest")
    total = inf_nfe.find("nfe:total/nfe:ICMSTot", NS) or inf_nfe.find(f"{{{NS['nfe']}}}total/{{{NS['nfe']}}}ICMSTot")
    transp = inf_nfe.find("nfe:transp", NS) or inf_nfe.find(f"{{{NS['nfe']}}}transp")
    cobr = inf_nfe.find("nfe:cobr", NS) or inf_nfe.find(f"{{{NS['nfe']}}}cobr")
    pag = inf_nfe.find("nfe:pag", NS) or inf_nfe.find(f"{{{NS['nfe']}}}pag")
    inf_adic = inf_nfe.find("nfe:infAdic", NS) or inf_nfe.find(f"{{{NS['nfe']}}}infAdic")

    # ---- Cabeçalho NFe (uma linha por NF) ----
    row_nfe = {
        "chave_NF": chave,
        "arquivo_origem": source_path or "",
        **_dict_from_children(ide, "ide"),
    }
    if emit is not None:
        row_nfe["emit_CNPJ"] = _text(emit.find("nfe:CNPJ", NS) or emit.find(f"{{{NS['nfe']}}}CNPJ"))
        row_nfe["emit_xNome"] = _text(emit.find("nfe:xNome", NS) or emit.find(f"{{{NS['nfe']}}}xNome"))
        row_nfe["emit_xFant"] = _text(emit.find("nfe:xFant", NS) or emit.find(f"{{{NS['nfe']}}}xFant"))
        ender = emit.find("nfe:enderEmit", NS) or emit.find(f"{{{NS['nfe']}}}enderEmit")
        if ender is not None:
            row_nfe["emit_UF"] = _text(ender.find("nfe:UF", NS) or ender.find(f"{{{NS['nfe']}}}UF"))
            row_nfe["emit_xMun"] = _text(ender.find("nfe:xMun", NS) or ender.find(f"{{{NS['nfe']}}}xMun"))
    if dest is not None:
        row_nfe["dest_CNPJ"] = _text(dest.find("nfe:CNPJ", NS) or dest.find(f"{{{NS['nfe']}}}CNPJ"))
        row_nfe["dest_xNome"] = _text(dest.find("nfe:xNome", NS) or dest.find(f"{{{NS['nfe']}}}xNome"))
        ender_dest = dest.find("nfe:enderDest", NS) or dest.find(f"{{{NS['nfe']}}}enderDest")
        row_nfe["dest_UF"] = _text(ender_dest.find("nfe:UF", NS) or ender_dest.find(f"{{{NS['nfe']}}}UF")) if ender_dest is not None else ""
    if total is not None:
        row_nfe["vNF"] = _text(total.find("nfe:vNF", NS) or total.find(f"{{{NS['nfe']}}}vNF"))
        row_nfe["vProd"] = _text(total.find("nfe:vProd", NS) or total.find(f"{{{NS['nfe']}}}vProd"))
        row_nfe["vICMS"] = _text(total.find("nfe:vICMS", NS) or total.find(f"{{{NS['nfe']}}}vICMS"))
        row_nfe["vPIS"] = _text(total.find("nfe:vPIS", NS) or total.find(f"{{{NS['nfe']}}}vPIS"))
        row_nfe["vCOFINS"] = _text(total.find("nfe:vCOFINS", NS) or total.find(f"{{{NS['nfe']}}}vCOFINS"))
        row_nfe["vFrete"] = _text(total.find("nfe:vFrete", NS) or total.find(f"{{{NS['nfe']}}}vFrete"))
        row_nfe["vDesc"] = _text(total.find("nfe:vDesc", NS) or total.find(f"{{{NS['nfe']}}}vDesc"))
    if inf_adic is not None:
        row_nfe["infCpl"] = _text(inf_adic.find("nfe:infCpl", NS) or inf_adic.find(f"{{{NS['nfe']}}}infCpl"))[:500]  # limitar tamanho
        row_nfe["infAdFisco"] = _text(inf_adic.find("nfe:infAdFisco", NS) or inf_adic.find(f"{{{NS['nfe']}}}infAdFisco"))[:500]

    # ---- Itens (detalhes): cada item vinculado à NF por chave_NF + nItem ----
    itens = []
    for det in inf_nfe.findall("nfe:det", NS) or inf_nfe.findall(f"{{{NS['nfe']}}}det"):
        n_item = det.get("nItem", "")
        prod = det.find("nfe:prod", NS) or det.find(f"{{{NS['nfe']}}}prod")
        imposto = det.find("nfe:imposto", NS) or det.find(f"{{{NS['nfe']}}}imposto")
        prod_dict = _dict_from_children(prod, "prod") if prod is not None else {}
        row_item = {
            "chave_NF": chave,
            "nItem": n_item,
            **prod_dict,
        }
        row_item["infAdProd"] = _text(det.find("nfe:infAdProd", NS) or det.find(f"{{{NS['nfe']}}}infAdProd"))
        row_item.update(_flatten_imposto(imposto))
        itens.append(row_item)

    # ---- Totais (uma linha por NF; resumo numérico) ----
    totais_row = {"chave_NF": chave}
    if total is not None:
        totais_row.update(_dict_from_children(total, "tot"))

    # ---- Transporte ----
    transp_rows = []
    if transp is not None:
        mod_frete = _text(transp.find("nfe:modFrete", NS) or transp.find(f"{{{NS['nfe']}}}modFrete"))
        transporta = transp.find("nfe:transporta", NS) or transp.find(f"{{{NS['nfe']}}}transporta")
        t_row = {"chave_NF": chave, "modFrete": mod_frete}
        if transporta is not None:
            t_row["transporta_CNPJ"] = _text(transporta.find("nfe:CNPJ", NS) or transporta.find(f"{{{NS['nfe']}}}CNPJ"))
            t_row["transporta_xNome"] = _text(transporta.find("nfe:xNome", NS) or transporta.find(f"{{{NS['nfe']}}}xNome"))
            t_row["transporta_UF"] = _text(transporta.find("nfe:UF", NS) or transporta.find(f"{{{NS['nfe']}}}UF"))
        for vol in transp.findall("nfe:vol", NS) or transp.findall(f"{{{NS['nfe']}}}vol"):
            vol_row = {**t_row, **_dict_from_children(vol, "vol")}
            transp_rows.append(vol_row)
        if not transp_rows:
            transp_rows.append(t_row)

    # ---- Duplicatas (cobr/dup) ----
    dup_rows = []
    if cobr is not None:
        for dup in cobr.findall("nfe:dup", NS) or cobr.findall(f"{{{NS['nfe']}}}dup"):
            dup_rows.append({
                "chave_NF": chave,
                "nDup": _text(dup.find("nfe:nDup", NS) or dup.find(f"{{{NS['nfe']}}}nDup")),
                "dVenc": _text(dup.find("nfe:dVenc", NS) or dup.find(f"{{{NS['nfe']}}}dVenc")),
                "vDup": _text(dup.find("nfe:vDup", NS) or dup.find(f"{{{NS['nfe']}}}vDup")),
            })

    # ---- Pagamento (detPag) ----
    pag_rows = []
    if pag is not None:
        for det_pag in pag.findall("nfe:detPag", NS) or pag.findall(f"{{{NS['nfe']}}}detPag"):
            pag_rows.append({
                "chave_NF": chave,
                "indPag": _text(det_pag.find("nfe:indPag", NS) or det_pag.find(f"{{{NS['nfe']}}}indPag")),
                "tPag": _text(det_pag.find("nfe:tPag", NS) or det_pag.find(f"{{{NS['nfe']}}}tPag")),
                "vPag": _text(det_pag.find("nfe:vPag", NS) or det_pag.find(f"{{{NS['nfe']}}}vPag")),
            })

    # ---- Referências (ide/NFref) ----
    ref_rows = []
    if ide is not None:
        for nfref in ide.findall("nfe:NFref", NS) or ide.findall(f"{{{NS['nfe']}}}NFref"):
            row_ref = {"chave_NF": chave}
            ref_nfe = nfref.find("nfe:refNFe", NS) or nfref.find(f"{{{NS['nfe']}}}refNFe")
            if ref_nfe is not None:
                row_ref["refNFe"] = _text(ref_nfe)
            ref_nf = nfref.find("nfe:refNF", NS) or nfref.find(f"{{{NS['nfe']}}}refNF")
            if ref_nf is not None:
                row_ref["refNF_CNPJ"] = _text(ref_nf.find("nfe:CNPJ", NS) or ref_nf.find(f"{{{NS['nfe']}}}CNPJ"))
                row_ref["refNF_nNF"] = _text(ref_nf.find("nfe:nNF", NS) or ref_nf.find(f"{{{NS['nfe']}}}nNF"))
                row_ref["refNF_serie"] = _text(ref_nf.find("nfe:serie", NS) or ref_nf.find(f"{{{NS['nfe']}}}serie"))
            if len(row_ref) > 1:
                ref_rows.append(row_ref)

    # ---- Protocolo (protNFe/infProt) ----
    prot_row = {"chave_NF": chave}
    if prot is not None:
        inf_prot = prot.find("nfe:infProt", NS) or prot.find(f"{{{NS['nfe']}}}infProt")
        if inf_prot is None:
            inf_prot = prot.find("infProt")  # sem namespace
        if inf_prot is not None:
            prot_row["nProt"] = _text(inf_prot.find("nfe:nProt", NS) or inf_prot.find(f"{{{NS['nfe']}}}nProt") or inf_prot.find("nProt"))
            prot_row["cStat"] = _text(inf_prot.find("nfe:cStat", NS) or inf_prot.find(f"{{{NS['nfe']}}}cStat") or inf_prot.find("cStat"))
            prot_row["xMotivo"] = _text(inf_prot.find("nfe:xMotivo", NS) or inf_prot.find(f"{{{NS['nfe']}}}xMotivo") or inf_prot.find("xMotivo"))
            prot_row["dhRecbto"] = _text(inf_prot.find("nfe:dhRecbto", NS) or inf_prot.find(f"{{{NS['nfe']}}}dhRecbto") or inf_prot.find("dhRecbto"))

    return {
        "nfe": [row_nfe],
        "itens": itens,
        "totais": [totais_row],
        "transporte": transp_rows,
        "duplicatas": dup_rows,
        "pagamento": pag_rows,
        "referencias": ref_rows,
        "protocolo": [prot_row],
    }


def parse_nfe_file(path: Union[str, Path]) -> Optional[Dict[str, List[dict]]]:
    """Carrega e faz parse de um arquivo XML de NFe."""
    path = Path(path)
    if not path.exists() or not path.suffix.lower() in (".xml",):
        return None
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        content = path.read_bytes()
    return parse_nfe_xml(content, source_path=str(path))

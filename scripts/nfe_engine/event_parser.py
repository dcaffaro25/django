# -*- coding: utf-8 -*-
"""
Parser de XML de evento NFe (cancelamento, CCe, manifestação do destinatário, etc.).
Suporta envEvento (pedido) e retEnvEvento (resposta SEFAZ).
"""
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Dict, Optional, Union

NS = {"nfe": "http://www.portalfiscal.inf.br/nfe"}
logger = logging.getLogger("billing.nfe_events")


def _text(el: Optional[ET.Element], default: str = "") -> str:
    if el is not None and el.text is not None:
        return (el.text or "").strip()
    return default


def _find_any(parent: Optional[ET.Element], *local_names: str) -> Optional[ET.Element]:
    """Encontra o primeiro filho/descendente com uma das tags (com ou sem namespace)."""
    if parent is None:
        return None
    uri = NS["nfe"]
    full_uri_prefix = "{" + uri + "}"
    for name in local_names:
        # Com prefixo nfe: é obrigatório passar namespaces no find()
        el = parent.find(f".//nfe:{name}", NS)
        if el is not None:
            return el
        # Com URI completo não precisa de prefix map
        el = parent.find(f".//{full_uri_prefix}{name}")
        if el is not None:
            return el
        el = parent.find(f".//{name}")
        if el is not None:
            return el
    return None


def _safe_int(val: Any, default: int = 0) -> int:
    if val is None or (isinstance(val, str) and not val.strip()):
        return default
    try:
        return int(float(str(val).strip().split(".")[0]))
    except (ValueError, TypeError):
        return default


def _safe_date(val: Any) -> Optional[datetime]:
    if not val or not str(val).strip():
        return None
    s = str(val).strip()
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _extract_from_inf_evento(inf_evento: Optional[ET.Element]) -> Dict[str, Any]:
    """Extrai campos comuns de um nó infEvento (pedido ou resposta)."""
    if inf_evento is None:
        return {}
    return {
        "chave_nfe": _text(_find_any(inf_evento, "chNFe"))[:44],
        "tipo_evento": _safe_int(_text(_find_any(inf_evento, "tpEvento")), 0),
        "n_seq_evento": max(1, _safe_int(_text(_find_any(inf_evento, "nSeqEvento")), 1)),
        "data_evento": _safe_date(_text(_find_any(inf_evento, "dhEvento"))),
        "data_registro": _safe_date(_text(_find_any(inf_evento, "dhRegEvento"))),
        "protocolo": _text(_find_any(inf_evento, "nProt"))[:20],
        "status_sefaz": _text(_find_any(inf_evento, "cStat"))[:5],
        "motivo_sefaz": _text(_find_any(inf_evento, "xMotivo"))[:500],
    }


def _extract_det_evento(inf_evento_pedido: Optional[ET.Element], tipo_evento: int) -> str:
    """Extrai descrição do detEvento: xJust (cancelamento) ou xCorrecao (CCe)."""
    if inf_evento_pedido is None:
        return ""
    det = _find_any(inf_evento_pedido, "detEvento")
    if det is None:
        return ""
    if tipo_evento == 110111:
        x_just = _text(_find_any(det, "xJust"))
        if x_just:
            return x_just[:5000]
        return _text(_find_any(det, "descEvento"))[:5000]
    if tipo_evento == 110110:
        return _text(_find_any(det, "xCorrecao"))[:5000]
    return _text(_find_any(det, "descEvento"))[:5000]


def parse_nfe_evento_xml(
    content: Union[str, bytes], source_path: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Faz parse de um XML de evento NFe.
    Suporta: procEventoNFe (pedido+retorno), envEvento (pedido), retEnvEvento (resposta).
    Para cancelamento (110111) preenche descricao com xJust; para CCe (110110) com xCorrecao.
    """
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        logger.debug("parse_nfe_evento_xml: ParseError %s source=%s", e, source_path)
        return None

    tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag
    logger.debug("parse_nfe_evento_xml: root tag=%r source=%s", tag, source_path)
    xml_str = content.decode("utf-8", errors="replace") if isinstance(content, bytes) else content
    arquivo = (source_path or "")[:500]

    inf_pedido = None
    inf_resposta = None

    if tag == "procEventoNFe":
        evento = root.find(".//nfe:evento", NS) or root.find(f".//{{{NS['nfe']}}}evento")
        if evento is not None:
            inf_pedido = _find_any(evento, "infEvento")
        ret_evento = root.find(".//nfe:retEvento", NS) or root.find(f".//{{{NS['nfe']}}}retEvento")
        if ret_evento is not None:
            inf_resposta = _find_any(ret_evento, "infEvento")
        if inf_pedido is None:
            inf_pedido = root.find(".//infEvento")
        all_inf = root.findall(f".//{{{NS['nfe']}}}infEvento") or root.findall(".//infEvento")
        if all_inf and inf_resposta is None and len(all_inf) >= 2:
            inf_resposta = all_inf[1]
    elif tag == "retEnvEvento":
        ret_evento = root.find(".//nfe:retEvento", NS) or root.find(f".//{{{NS['nfe']}}}retEvento")
        if ret_evento is not None:
            inf_resposta = _find_any(ret_evento, "infEvento", "retInfEvento")
        if inf_resposta is None:
            inf_resposta = root.find(".//infEvento") or root.find(".//retInfEvento")
        inf_pedido = inf_resposta
    elif tag == "envEvento":
        evento = root.find(".//nfe:evento", NS) or root.find(f".//{{{NS['nfe']}}}evento")
        if evento is not None:
            inf_pedido = _find_any(evento, "infEvento")
        if inf_pedido is None:
            inf_pedido = root.find(".//infEvento")
    else:
        all_inf = root.findall(f".//{{{NS['nfe']}}}infEvento") or root.findall(".//infEvento")
        if all_inf:
            inf_pedido = all_inf[0]
            if len(all_inf) >= 2:
                inf_resposta = all_inf[1]
            else:
                inf_resposta = inf_pedido
        else:
            inf_pedido = _find_any(root, "infEvento", "retInfEvento")
            inf_resposta = inf_pedido

    if inf_pedido is None:
        logger.debug(
            "parse_nfe_evento_xml: infEvento não encontrado (tag=%r) source=%s",
            tag,
            source_path,
        )
        return None

    req = _extract_from_inf_evento(inf_pedido)
    res = _extract_from_inf_evento(inf_resposta) if inf_resposta is not None else {}
    chave_nfe = req.get("chave_nfe") or res.get("chave_nfe") or ""
    if len(chave_nfe) != 44:
        logger.debug(
            "parse_nfe_evento_xml: chave_nfe inválida len=%s (esperado 44) source=%s",
            len(chave_nfe),
            source_path,
        )
        return None

    tipo_evento = req.get("tipo_evento") or res.get("tipo_evento") or 0
    n_seq_evento = req.get("n_seq_evento") or res.get("n_seq_evento") or 1
    data_evento = req.get("data_evento") or res.get("data_evento")
    data_registro = res.get("data_registro")
    if data_evento is None and data_registro is not None:
        data_evento = data_registro
    protocolo = res.get("protocolo") or req.get("protocolo") or ""
    status_sefaz = res.get("status_sefaz") or req.get("status_sefaz") or ""
    motivo_sefaz = res.get("motivo_sefaz") or req.get("motivo_sefaz") or ""

    descricao = _extract_det_evento(inf_pedido, tipo_evento)
    if not descricao and motivo_sefaz:
        descricao = motivo_sefaz

    return {
        "chave_nfe": chave_nfe,
        "tipo_evento": tipo_evento,
        "n_seq_evento": n_seq_evento,
        "data_evento": data_evento,
        "descricao": descricao[:5000] if descricao else "",
        "protocolo": protocolo,
        "status_sefaz": status_sefaz,
        "motivo_sefaz": motivo_sefaz,
        "data_registro": data_registro,
        "xml_original": xml_str,
        "arquivo_origem": arquivo,
    }

# -*- coding: utf-8 -*-
"""
Parser de XML de inutilização de numeração NFe (ProcInutNFe).
"""
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Dict, Optional, Union

NS = {"nfe": "http://www.portalfiscal.inf.br/nfe"}


def _text(el: Optional[ET.Element], default: str = "") -> str:
    if el is not None and el.text is not None:
        return (el.text or "").strip()
    return default


def _find_any(parent: Optional[ET.Element], *local_names: str) -> Optional[ET.Element]:
    if parent is None:
        return None
    for name in local_names:
        for prefix in ("nfe:", "{" + NS["nfe"] + "}"):
            el = parent.find(f".//{prefix}{name}")
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


def parse_nfe_inut_xml(
    content: Union[str, bytes], source_path: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Faz parse de um XML ProcInutNFe (inutilização de numeração).
    Retorna dict com: cuf, ano, cnpj, modelo, serie, n_nf_ini, n_nf_fin, x_just,
    protocolo, status_sefaz, motivo_sefaz, data_registro, xml_original, arquivo_origem.
    """
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return None

    tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag
    if tag.lower() not in ("procinutnfe", "inutnfe"):
        return None

    inf_inut = _find_any(root, "infInut")
    if inf_inut is None:
        return None

    ret_inut = root.find(".//nfe:retInutNFe", NS) or root.find(f".//{{{NS['nfe']}}}retInutNFe")
    inf_ret = None
    if ret_inut is not None:
        inf_ret = _find_any(ret_inut, "infInut")
    if inf_ret is None:
        inf_ret = root.find(".//retInutNFe/infInut") or root.find(".//infInut")
        if inf_ret is not None and inf_ret == inf_inut:
            inf_ret = None
    all_inf = root.findall(f".//{{{NS['nfe']}}}infInut") or root.findall(".//infInut")
    if len(all_inf) >= 2:
        inf_ret = all_inf[1]

    ano = _text(_find_any(inf_inut, "ano"))[:2]
    serie = _safe_int(_text(_find_any(inf_inut, "serie")), 1)
    n_ini = _safe_int(_text(_find_any(inf_inut, "nNFIni")))
    n_fin = _safe_int(_text(_find_any(inf_inut, "nNFFin")))
    if not ano or n_ini <= 0 or n_fin < n_ini:
        return None

    cnpj = _text(_find_any(inf_inut, "CNPJ"))[:14]
    if not cnpj:
        return None

    protocolo = ""
    status_sefaz = ""
    motivo_sefaz = ""
    data_registro = None
    if inf_ret is not None:
        protocolo = _text(_find_any(inf_ret, "nProt"))[:20]
        status_sefaz = _text(_find_any(inf_ret, "cStat"))[:5]
        motivo_sefaz = _text(_find_any(inf_ret, "xMotivo"))[:500]
        data_registro = _safe_date(_text(_find_any(inf_ret, "dhRecbto")))

    return {
        "cuf": _text(_find_any(inf_inut, "cUF"))[:2],
        "ano": ano,
        "cnpj": cnpj,
        "modelo": _safe_int(_text(_find_any(inf_inut, "mod")), 55),
        "serie": serie,
        "n_nf_ini": n_ini,
        "n_nf_fin": n_fin,
        "x_just": _text(_find_any(inf_inut, "xJust"))[:255],
        "protocolo": protocolo,
        "status_sefaz": status_sefaz,
        "motivo_sefaz": motivo_sefaz,
        "data_registro": data_registro,
        "xml_original": content.decode("utf-8", errors="replace") if isinstance(content, bytes) else content,
        "arquivo_origem": (source_path or "")[:500],
    }

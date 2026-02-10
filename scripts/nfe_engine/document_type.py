# -*- coding: utf-8 -*-
"""
Detecção do tipo de documento XML NFe para roteamento do parser correto.
"""
import xml.etree.ElementTree as ET
from typing import Optional, Union

# Valores possíveis: "nfe" | "evento" | "inutilizacao" | None
TIPO_NFE = "nfe"
TIPO_EVENTO = "evento"
TIPO_INUTILIZACAO = "inutilizacao"


def detect_nfe_document_type(content: Union[str, bytes]) -> Optional[str]:
    """
    Inspeciona o root do XML e retorna o tipo do documento:
    - "nfe"          : NFe ou procNFe (nota com protocolo)
    - "evento"       : procEventoNFe, envEvento ou retEnvEvento
    - "inutilizacao" : ProcInutNFe (inutilização de numeração)
    - None           : não reconhecido ou erro de parse
    """
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return None
    tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag
    tag_lower = tag.lower()
    if tag_lower in ("nfe", "nfeproc", "procnfe"):
        return TIPO_NFE
    if tag_lower in ("proceventonfe", "envevento", "retenvevento"):
        return TIPO_EVENTO
    if tag_lower in ("procinutnfe", "inutnfe", "retinutnfe"):
        return TIPO_INUTILIZACAO
    # Fallback: presença de elementos característicos
    ns = "http://www.portalfiscal.inf.br/nfe"
    if root.find(f".//{{{ns}}}infNFe") is not None or root.find(".//infNFe") is not None:
        return TIPO_NFE
    if root.find(f".//{{{ns}}}infEvento") is not None or root.find(".//infEvento") is not None:
        return TIPO_EVENTO
    if root.find(f".//{{{ns}}}infInut") is not None or root.find(".//infInut") is not None:
        return TIPO_INUTILIZACAO
    return None

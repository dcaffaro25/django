# -*- coding: utf-8 -*-
"""Testa parsers de evento e inutilização com XMLs reais."""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nord_backend.settings")
django.setup()

from scripts.nfe_engine import (
    detect_nfe_document_type,
    parse_nfe_evento_xml,
    parse_nfe_inut_xml,
)

# ProcInutNFe mínimo (estrutura real)
INUT_XML = """<?xml version="1.0" encoding="UTF-8"?><ProcInutNFe versao="4.00" xmlns="http://www.portalfiscal.inf.br/nfe"><inutNFe versao="4.00"><infInut Id="ID35253623039100018855001000029606000029606"><tpAmb>1</tpAmb><xServ>INUTILIZAR</xServ><cUF>35</cUF><ano>25</ano><CNPJ>36230391000188</CNPJ><mod>55</mod><serie>1</serie><nNFIni>29606</nNFIni><nNFFin>29606</nNFFin><xJust>dados incorretos</xJust></infInut></inutNFe><retInutNFe versao="4.00"><infInut><tpAmb>1</tpAmb><verAplic>SP_NFE_PL009_V4</verAplic><cStat>102</cStat><xMotivo>Inutilização de número homologado</xMotivo><cUF>35</cUF><ano>25</ano><CNPJ>36230391000188</CNPJ><mod>55</mod><serie>1</serie><nNFIni>29606</nNFIni><nNFFin>29606</nNFFin><dhRecbto>2025-04-07T17:47:26-03:00</dhRecbto><nProt>135250919497385</nProt></infInut></retInutNFe></ProcInutNFe>"""

# procEventoNFe cancelamento (estrutura real)
EVENTO_XML = """<?xml version="1.0" encoding="UTF-8"?><procEventoNFe versao="1.00" xmlns="http://www.portalfiscal.inf.br/nfe"><evento versao="1.00"><infEvento Id="ID1101113525013623039100018855001000036079107346258701"><cOrgao>35</cOrgao><tpAmb>1</tpAmb><CNPJ>36230391000188</CNPJ><chNFe>35250136230391000188550010000360791073462587</chNFe><dhEvento>2025-01-15T17:38:09-03:00</dhEvento><tpEvento>110111</tpEvento><nSeqEvento>1</nSeqEvento><verEvento>1.00</verEvento><detEvento versao="1.00"><descEvento>Cancelamento</descEvento><nProt>135250132877598</nProt><xJust>dados incorretos</xJust></detEvento></infEvento></evento><retEvento versao="1.00"><infEvento><tpAmb>1</tpAmb><verAplic>SP_EVENTOS_PL_100</verAplic><cOrgao>35</cOrgao><cStat>135</cStat><xMotivo>Evento registrado e vinculado a NF-e</xMotivo><chNFe>35250136230391000188550010000360791073462587</chNFe><tpEvento>110111</tpEvento><xEvento>Cancelamento registrado</xEvento><nSeqEvento>1</nSeqEvento><dhRegEvento>2025-01-15T17:38:09-03:00</dhRegEvento><nProt>135250134358457</nProt></infEvento></retEvento></procEventoNFe>"""


def main():
    print("=== Detecção de tipo ===")
    print("Evento:", detect_nfe_document_type(EVENTO_XML.encode("utf-8")))
    print("Inut:  ", detect_nfe_document_type(INUT_XML.encode("utf-8")))

    print("\n=== Parse evento (cancelamento) ===")
    ev = parse_nfe_evento_xml(EVENTO_XML)
    if ev:
        print("  chave_nfe:", ev.get("chave_nfe"))
        print("  tipo_evento:", ev.get("tipo_evento"))
        print("  descricao (xJust):", repr(ev.get("descricao")))
        print("  protocolo:", ev.get("protocolo"))
        print("  status_sefaz:", ev.get("status_sefaz"))
    else:
        print("  FALHOU")

    print("\n=== Parse inutilização ===")
    inut = parse_nfe_inut_xml(INUT_XML)
    if inut:
        print("  ano:", inut.get("ano"), "serie:", inut.get("serie"))
        print("  n_nf_ini..n_nf_fin:", inut.get("n_nf_ini"), "..", inut.get("n_nf_fin"))
        print("  x_just:", repr(inut.get("x_just")))
        print("  protocolo:", inut.get("protocolo"))
        print("  status_sefaz:", inut.get("status_sefaz"))
        print("  data_registro:", inut.get("data_registro"))
    else:
        print("  FALHOU")

    print("\nOK" if (ev and inut) else "VERIFICAR PARSERS")


if __name__ == "__main__":
    main()

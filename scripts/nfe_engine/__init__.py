# Engine para processar XMLs de NFe e exportar para Excel
from .parser import parse_nfe_xml, parse_nfe_file
from .excel_export import export_to_excel
from .event_parser import parse_nfe_evento_xml
from .inut_parser import parse_nfe_inut_xml
from .document_type import detect_nfe_document_type

__all__ = [
    "parse_nfe_xml",
    "parse_nfe_file",
    "export_to_excel",
    "parse_nfe_evento_xml",
    "parse_nfe_inut_xml",
    "detect_nfe_document_type",
]

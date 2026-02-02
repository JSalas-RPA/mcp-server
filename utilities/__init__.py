# utilities/__init__.py
# ============================================================================
# Módulo de utilidades - Funciones auxiliares internas
# ============================================================================
# Estas NO son tools, son funciones de soporte interno.
# Para tools, ver tools.py
# ============================================================================

# Text utilities
from utilities.text_utils import (
    calcular_similitud_nombres,
    limpiar_nombre_minimo,
    extraer_solo_numeros,
    clean_openai_json,
    calcular_similitud_descripcion,
    comparar_precios_unitarios,
    evaluar_cantidad,
    evaluar_monto_total,
)

# Date utilities
from utilities.date_utils import (
    format_sap_date,
)

# SAP client utilities
from utilities.sap_client import (
    SAP_CONFIG,
    safe_json_response,
    obtener_sesion_con_token,
    get_sap_auth,
    get_sap_headers,
)

# OCR utilities (nuevo módulo)
from utilities.ocr import (
    get_transcript_document,
    get_transcript_document_cloud_vision,
    extract_text_from_first_page,
)

# LLM client utilities (nuevo módulo)
from utilities.llm_client import (
    get_openai_answer,
    get_clean_json,
    extraer_datos_factura_desde_texto,
    validar_proveedor_con_ai,
    comparar_descripciones_con_ia,
)

# Storage utilities
from utilities.file_storage import (
    upload_file_base64_to_gcs,
    download_pdf_to_tempfile,
)

# Prompts
from utilities.prompts import (
    get_invoice_validator_prompt,
    get_invoice_text_parser_prompt,
    get_OC_validator_prompt,
    get_material_entry_validator_prompt,
    get_description_comparison_prompt,
)

__all__ = [
    # text_utils
    'calcular_similitud_nombres',
    'limpiar_nombre_minimo',
    'extraer_solo_numeros',
    'clean_openai_json',
    'calcular_similitud_descripcion',
    'comparar_precios_unitarios',
    'evaluar_cantidad',
    'evaluar_monto_total',
    # date_utils
    'format_sap_date',
    # sap_client
    'SAP_CONFIG',
    'safe_json_response',
    'obtener_sesion_con_token',
    'get_sap_auth',
    'get_sap_headers',
    # ocr
    'get_transcript_document',
    'get_transcript_document_cloud_vision',
    'extract_text_from_first_page',
    # llm_client
    'get_openai_answer',
    'get_clean_json',
    'extraer_datos_factura_desde_texto',
    'validar_proveedor_con_ai',
    'comparar_descripciones_con_ia',
    # file_storage
    'upload_file_base64_to_gcs',
    'download_pdf_to_tempfile',
    # prompts
    'get_invoice_validator_prompt',
    'get_invoice_text_parser_prompt',
    'get_OC_validator_prompt',
    'get_material_entry_validator_prompt',
    'get_description_comparison_prompt',
]

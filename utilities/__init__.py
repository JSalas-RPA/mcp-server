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

# OCR and AI utilities (from general.py)
from utilities.general import (
    get_transcript_document,
    get_transcript_document_cloud_vision,
    get_openai_answer,
    get_clean_json,
)

# Storage utilities
from utilities.image_storage import (
    upload_file_base64_to_gcs,
    download_pdf_to_tempfile,
)

# Prompts
from utilities.prompts import (
    get_invoice_validator_prompt,
    get_invoice_text_parser_prompt,
    get_OC_validator_prompt,
    get_material_entry_validator_prompt,
)

__all__ = [
    # text_utils
    'calcular_similitud_nombres',
    'limpiar_nombre_minimo',
    'extraer_solo_numeros',
    'clean_openai_json',
    # date_utils
    'format_sap_date',
    # sap_client
    'SAP_CONFIG',
    'safe_json_response',
    'obtener_sesion_con_token',
    'get_sap_auth',
    'get_sap_headers',
    # general
    'get_transcript_document',
    'get_transcript_document_cloud_vision',
    'get_openai_answer',
    'get_clean_json',
    # image_storage
    'upload_file_base64_to_gcs',
    'download_pdf_to_tempfile',
    # prompts
    'get_invoice_validator_prompt',
    'get_invoice_text_parser_prompt',
    'get_OC_validator_prompt',
    'get_material_entry_validator_prompt',
]

# utilities/sap_client.py
# ============================================
# Configuración y cliente para SAP S4HANA
# ============================================

import os
import json
import logging
import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)

# Intentar cargar .env si python-dotenv está instalado
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ============================================
# CONFIGURACIÓN DE ENDPOINTS SAP
# ============================================
SAP_CONFIG = {
    'username': os.getenv('SAP_USERNAME', ''),
    'password': os.getenv('SAP_PASSWORD', ''),
    'supplier_url': os.getenv(
        'SAP_SUPPLIER_URL',
        'https://my408830-api.s4hana.cloud.sap/sap/opu/odata/sap/API_BUSINESS_PARTNER/A_Supplier'
    ),
    'purchase_order_url': os.getenv(
        'SAP_PURCHASE_ORDER_URL',
        'https://my408830-api.s4hana.cloud.sap/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV/A_PurchaseOrder'
    ),
    'invoice_post_url': os.getenv(
        'SAP_INVOICE_POST_URL',
        'https://my408830-api.s4hana.cloud.sap/sap/opu/odata/sap/API_SUPPLIERINVOICE_PROCESS_SRV/A_SupplierInvoice'
    ),
    'material_doc_url': os.getenv(
        'SAP_MATERIAL_DOC_URL',
        'https://my408830-api.s4hana.cloud.sap/sap/opu/odata/sap/API_MATERIAL_DOCUMENT_SRV/A_MaterialDocumentItem'
    )
}


def safe_json_response(response: requests.Response) -> dict | None:
    """
    Valida que la respuesta HTTP contenga JSON y maneja errores.
    """
    try:
        return response.json()
    except json.JSONDecodeError:
        logger.error(f"Respuesta no es JSON válido. Status: {response.status_code}")
        logger.error(f"Contenido: {response.text[:500]}")
        return None
    except Exception as e:
        logger.error(f"Excepción al parsear respuesta JSON: {str(e)}")
        return None


def obtener_sesion_con_token() -> tuple[requests.Session | None, str | None]:
    """
    Obtiene una sesión con token CSRF válido para SAP.
    Retorna (session, token) o (None, None) si falla.
    """
    session = requests.Session()
    session.auth = HTTPBasicAuth(SAP_CONFIG['username'], SAP_CONFIG['password'])

    try:
        headers_get = {
            "Accept": "application/json",
            "x-csrf-token": "Fetch"
        }

        logger.info("Obteniendo token CSRF de SAP...")
        response = session.get(
            SAP_CONFIG['invoice_post_url'],
            headers=headers_get,
            timeout=30
        )

        if response.status_code != 200:
            logger.error(f"Error al obtener token CSRF: {response.status_code}")
            logger.error(f"Respuesta: {response.text[:200]}")
            return None, None

        token = response.headers.get("x-csrf-token")
        if not token:
            logger.error("No se encontró x-csrf-token en los headers de SAP")
            return None, None

        logger.info("✓ Token CSRF obtenido exitosamente")
        return session, token

    except Exception as e:
        logger.error(f"Error al obtener sesión con token: {e}")
        return None, None


def get_sap_auth() -> HTTPBasicAuth:
    """
    Retorna objeto de autenticación básica para SAP.
    """
    return HTTPBasicAuth(SAP_CONFIG['username'], SAP_CONFIG['password'])


def get_sap_headers(include_csrf: bool = False, csrf_token: str = None) -> dict:
    """
    Retorna headers estándar para llamadas a SAP API.
    """
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    if include_csrf and csrf_token:
        headers["x-csrf-token"] = csrf_token
    return headers

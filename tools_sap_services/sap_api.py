# services/sap_api.py
# ============================================
# Llamadas HTTP a SAP S4HANA API
# ============================================
# Este módulo contiene SOLO las llamadas HTTP puras a SAP.
# La lógica de negocio (scoring, filtrado) está en otros módulos.
# ============================================

import json
import logging
import requests

from utilities.sap_client import (
    SAP_CONFIG,
    safe_json_response,
    obtener_sesion_con_token,
    get_sap_auth,
    get_sap_headers,
)

logger = logging.getLogger(__name__)


# ============================================
# PROVEEDORES
# ============================================

def obtener_proveedores_sap() -> list:
    """
    Obtiene todos los proveedores desde SAP API.

    Returns:
        Lista de proveedores o lista vacía si hay error
    """
    try:
        headers = get_sap_headers()

        logger.info("Obteniendo lista de proveedores desde SAP...")
        response = requests.get(
            SAP_CONFIG['supplier_url'],
            headers=headers,
            auth=get_sap_auth(),
            timeout=30
        )

        if response.status_code == 200:
            data = safe_json_response(response)
            if data:
                proveedores = data.get("d", {}).get("results", [])
                logger.info(f"{len(proveedores)} proveedores obtenidos de SAP")

                print("\n" + "=" * 70)
                print("PROVEEDORES OBTENIDOS DE SAP (primeros 10):")
                print("=" * 70)
                for i, proveedor in enumerate(proveedores[:10]):
                    supplier_name = proveedor.get('SupplierName') or proveedor.get('BusinessPartnerName') or "N/A"
                    supplier_code = proveedor.get('Supplier') or proveedor.get('BusinessPartner') or "N/A"
                    tax_number = proveedor.get('TaxNumber1') or proveedor.get('TaxNumber') or "N/A"

                    print(f"  {i + 1:2d}. {supplier_name[:40]:40} | Codigo: {supplier_code:10} | Tax: {tax_number}")
                if len(proveedores) > 10:
                    print(f"  ... y {len(proveedores) - 10} mas")
                print("=" * 70)

                return proveedores
        else:
            logger.error(f"Error {response.status_code} al obtener proveedores de SAP")
            print(f"\nError al obtener proveedores: Status {response.status_code}")
            print(f"   Respuesta: {response.text[:200]}")

    except Exception as e:
        logger.error(f"Excepcion en obtener_proveedores_sap: {e}")

    return []


# ============================================
# ORDENES DE COMPRA
# ============================================

def fetch_ordenes_compra(supplier_code: str) -> dict:
    """
    Obtiene las órdenes de compra de un proveedor desde SAP.

    Args:
        supplier_code: Código del proveedor en SAP

    Returns:
        dict con estructura:
        {
            "status": "success" | "error",
            "data": lista de OCs con ítems expandidos,
            "error": mensaje de error (si aplica)
        }
    """
    if not supplier_code:
        return {"status": "error", "error": "No se proporciono codigo de proveedor"}

    try:
        headers = get_sap_headers()

        # Obtener OCs con ítems expandidos
        url = f"{SAP_CONFIG['purchase_order_url']}?$filter=Supplier eq '{supplier_code}'&$expand=to_PurchaseOrderItem"

        print(f"\n  Consultando SAP...")
        print(f"     URL: {url[:80]}...")

        response = requests.get(
            url,
            headers=headers,
            auth=get_sap_auth(),
            timeout=30
        )

        print(f"     Status: {response.status_code}")

        if response.status_code != 200:
            if response.status_code == 403:
                return {"status": "error", "error": "Permisos insuficientes (403)"}
            return {"status": "error", "error": f"Error SAP: {response.status_code}"}

        data = safe_json_response(response)
        if not data or "d" not in data or "results" not in data["d"]:
            return {"status": "success", "data": []}

        oc_list = data["d"]["results"]
        print(f"\n  OCs encontradas: {len(oc_list)}")

        return {"status": "success", "data": oc_list}

    except Exception as e:
        logger.error(f"Error en fetch_ordenes_compra: {e}")
        return {"status": "error", "error": str(e)}


# ============================================
# ENTRADAS DE MATERIAL (MIGO)
# ============================================

def fetch_entradas_material(
        purchase_order: str, 
        purchase_order_item: str = None, 
        movement_type: str = None, 
        quantity: str = None,
        material: str = None,
        ) -> dict:
    """
    Obtiene las entradas de material (MIGO) para una orden de compra.

    Args:
        purchase_order: Número de orden de compra
        purchase_order_item: Número de ítem (opcional)
        movement_type: Tipo de movimiento (opcional)
        quantity: Cantidad (opcional)
        material: Código de material (opcional)

    Returns:
        dict con estructura:
        {
            "status": "success" | "error",
            "data": lista de entradas de material,
            "error": mensaje de error (si aplica)
        }
    """
    if not purchase_order:
        return {"status": "error", "error": "No se proporciono orden de compra"}

    try:
        headers = get_sap_headers()

        # Construir filtro
        filtro = f"PurchaseOrder eq '{purchase_order}'"
        if purchase_order_item:
            filtro += f" and PurchaseOrderItem eq '{purchase_order_item}'"
        if movement_type:
            filtro += f" and GoodsMovementType eq '{movement_type}'"
        if quantity:
            filtro += f" and QuantityInBaseUnit eq {quantity}"
        if material:
            filtro += f" and Material eq '{material}'"

        url = f"{SAP_CONFIG['material_doc_url']}?$filter={filtro}"

        print(f"\n  Consultando entradas de material...")
        print(f"     OC: {purchase_order},\n Item: {purchase_order_item or 'todos'},\n Movimiento: {movement_type or 'cualquiera'},\n Cantidad: {quantity or 'cualquiera'},\n Material: {material or 'cualquiera'}")
        print(f"     URL: {url}")

        response = requests.get(
            url,
            headers=headers,
            auth=get_sap_auth(),
            timeout=30
        )

        if response.status_code != 200:
            return {"status": "error", "error": f"Error SAP: {response.status_code}"}

        data = safe_json_response(response)
        if not data or "d" not in data:
            return {"status": "success", "data": []}

        entradas = data["d"].get("results", [])
        print(f"     Entradas encontradas: {len(entradas)}")

        return {"status": "success", "data": entradas}

    except Exception as e:
        logger.error(f"Error en fetch_entradas_material: {e}")
        return {"status": "error", "error": str(e)}


def fetch_header_material(material_document: str, material_document_year: str) -> dict:
    """
    Obtiene el header de un documento de material para fechas y detalles.

    Args:
        material_document: Número del documento de material
        material_document_year: Año fiscal del documento

    Returns:
        dict con datos del header o vacío si no se encuentra
    """
    try:
        headers = get_sap_headers()
        url = f"{SAP_CONFIG['material_doc_url'].replace('/A_MaterialDocumentItem', '/A_MaterialDocumentHeader')}"
        url += f"(MaterialDocument='{material_document}',MaterialDocumentYear='{material_document_year}')"
        print(f"\n  Consultando header de documento de material...")
        print(f"     URL: {url}")
        response = requests.get(
            url,
            headers=headers,
            auth=get_sap_auth(),
            timeout=30
        )

        if response.status_code == 200:
            data = safe_json_response(response)
            if data and "d" in data:
                return data["d"]

        return {}

    except Exception as e:
        logger.warning(f"Error obteniendo header de material document: {e}")
        return {}


# ============================================
# VERIFICACION DE FACTURA DUPLICADA
# ============================================

def buscar_factura_existente(invoice_id: str, supplier_code: str) -> dict:
    """
    Busca si ya existe un MIRO (Supplier Invoice) en SAP con el mismo
    numero de factura y proveedor, para evitar duplicados.

    Args:
        invoice_id: Numero de factura del proveedor (SupplierInvoiceIDByInvcgParty)
        supplier_code: Codigo del proveedor en SAP (InvoicingParty)

    Returns:
        dict con estructura:
        {
            "status": "exists" | "not_found" | "error",
            "data": datos del MIRO existente (si aplica),
            "error": mensaje de error (si aplica)
        }
    """
    if not invoice_id or not supplier_code:
        return {"status": "error", "error": "Se requiere invoice_id y supplier_code"}

    try:
        headers = get_sap_headers()

        filtro = (
            f"SupplierInvoiceIDByInvcgParty eq '{invoice_id}' "
            f"and InvoicingParty eq '{supplier_code}'"
        )
        select = (
            "SupplierInvoice,FiscalYear,SupplierInvoiceIDByInvcgParty,"
            "InvoicingParty,InvoiceGrossAmount,PostingDate,DocumentDate"
        )
        url = f"{SAP_CONFIG['invoice_post_url']}?$filter={filtro}&$top=1&$select={select}"

        print(f"\n  Verificando factura duplicada en SAP...")
        print(f"     Factura: {invoice_id} | Proveedor: {supplier_code}")

        response = requests.get(
            url,
            headers=headers,
            auth=get_sap_auth(),
            timeout=30
        )

        if response.status_code != 200:
            logger.error(f"Error {response.status_code} al buscar factura existente")
            return {"status": "error", "error": f"Error SAP: {response.status_code}"}

        data = safe_json_response(response)
        if not data or "d" not in data:
            return {"status": "not_found"}

        resultados = data["d"].get("results", [])

        if resultados:
            miro = resultados[0]
            print(f"     MIRO encontrado: {miro.get('SupplierInvoice')} (Año: {miro.get('FiscalYear')})")
            return {"status": "exists", "data": miro}

        print(f"     No se encontro MIRO existente.")
        return {"status": "not_found"}

    except Exception as e:
        logger.error(f"Error en buscar_factura_existente: {e}")
        return {"status": "error", "error": str(e)}


# ============================================
# ENVIO DE FACTURA
# ============================================

def enviar_factura_a_sap(factura_json: dict) -> dict | None:
    """
    Envía la factura a SAP usando token CSRF y sesión persistente.

    Args:
        factura_json: JSON de la factura en formato SAP

    Returns:
        Respuesta de SAP si es exitosa (201 Created), None si hay error
    """
    session, token = obtener_sesion_con_token()
    if not session or not token:
        logger.error("No se pudo obtener sesion con token valido para SAP")
        return None

    try:
        headers_post = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-csrf-token": token
        }

        print("\n" + "=" * 70)
        print("ENVIANDO FACTURA A SAP")
        print("=" * 70)
        print("  Enviando JSON a SAP...")

        print("  JSON a enviar (resumen):")
        print(f"     CompanyCode: {factura_json.get('CompanyCode')}")
        print(f"     DocumentDate: {factura_json.get('DocumentDate')}")
        print(f"     SupplierInvoiceIDByInvcgParty: {factura_json.get('SupplierInvoiceIDByInvcgParty')}")
        print(f"     InvoicingParty: {factura_json.get('InvoicingParty')}")
        assignment_ref = factura_json.get('AssignmentReference', '')
        print(f"     AssignmentReference: {assignment_ref[:30] if assignment_ref else 'N/A'}...")
        print(f"     InvoiceGrossAmount: {factura_json.get('InvoiceGrossAmount')}")
        print(f"     Items: {len(factura_json.get('to_SuplrInvcItemPurOrdRef', {}).get('results', []))}")

        logger.info("Enviando factura a SAP...")

        response = session.post(
            SAP_CONFIG['invoice_post_url'],
            headers=headers_post,
            json={"d": factura_json},
            timeout=30
        )

        print(f"  Respuesta de SAP: Status {response.status_code}")
        logger.info(f"Respuesta de SAP: Status {response.status_code}")

        if response.status_code in [200, 201]:
            print("  Factura creada exitosamente en SAP")
            logger.info("Factura creada exitosamente en SAP")
            data = safe_json_response(response)
            #print(f"  Detalles respuesta SAP: {json.dumps(data, indent=2)}") # Descomentar para debug
            return data
        else:
            print(f"  Error al crear factura en SAP: {response.status_code}")
            logger.error(f"Error al crear factura en SAP: {response.status_code}")
            print(f"  Detalles: {response.text[:500]}")
            logger.error(f"Detalles: {response.text[:500]}")
            error_info = safe_json_response(response)
            if error_info:
                return error_info
            return None

    except Exception as e:
        logger.error(f"Error en envio a SAP: {e}")
        return None
    finally:
        if session:
            session.close()

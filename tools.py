# ============================================================================
# tools.py - Catálogo de Tools MCP Dsuite
# ============================================================================
# Autor: Equipo de Automation - Datec
# Fecha: 2026-01-16
# Descripción: Catálogo centralizado de todas las funciones que pueden ser
#              utilizadas como tools MCP.
#
# USO:
#   - Todas las funciones aquí pueden convertirse en tools MCP
#   - Para ACTIVAR una tool: importarla en server.py y decorar con @mcp.tool()
#   - Estado [ACTIVA]: Actualmente registrada en server.py
#   - Estado [RESERVA]: Disponible pero no registrada actualmente
#   - Estado [DEPRECADA]: No usar, mantener solo por compatibilidad
#
# BÚSQUEDA RÁPIDA:
#   - SECCIÓN 1: Extracción de documentos (PDF, imágenes, OCR)
#   - SECCIÓN 2: Parsing y estructuración de datos
#   - SECCIÓN 3: Validación SAP (proveedores, OC)
#   - SECCIÓN 4: Construcción y envío a SAP
#   - SECCIÓN 5: Flujos completos (orquestación)
# ============================================================================

import os
import logging

from utilities.ocr import get_transcript_document_cloud_vision
from utilities.file_storage import download_pdf_to_tempfile
from utilities.email_client import EmailClient
from services.sap_operations import (
    extraer_datos_factura_desde_texto,
    obtener_proveedores_sap,
    buscar_proveedor_en_sap,
    obtener_ordenes_compra_proveedor,
    verificar_entradas_material,
    construir_json_factura_sap,
    enviar_factura_a_sap,
)

logger = logging.getLogger(__name__)


# ============================================================================
# SECCIÓN 1: EXTRACCIÓN DE DOCUMENTOS
# ============================================================================
# Tools para extraer contenido de archivos (PDF, imágenes, etc.)
# ============================================================================

def extraer_texto_pdf(ruta_gcs: str) -> dict:
    """
    [ACTIVA] Extrae texto de un PDF usando OCR (Google Cloud Vision).

    Args:
        ruta_gcs: Ruta al PDF. Soporta:
            - gs://bucket/path/file.pdf
            - https://storage.googleapis.com/bucket/path/file.pdf
            - Ruta local existente
            - Blob relativo (ej: 'entrada_facturas/archivo.pdf')

    Returns:
        dict con keys:
            - status: "success" o "error"
            - data: texto extraído (si success)
            - error: mensaje de error (si error)
    """
    ruta_temp = None
    try:
        logger.info(f"Iniciando extracción de texto desde: {ruta_gcs}")

        # Descargar PDF temporalmente
        ruta_temp = download_pdf_to_tempfile(ruta_gcs)
        logger.info(f"Archivo temporal descargado: {ruta_temp}")

        # OCR con Cloud Vision
        logger.info("Extrayendo texto con Cloud Vision")
        texto_factura = get_transcript_document_cloud_vision(ruta_temp)
        logger.info(f"Texto extraído (primeros 2000 caracteres):\n{texto_factura[:2000]}")

        return {
            "status": "success",
            "data": texto_factura
        }

    except Exception as e:
        error_msg = f"Error al extraer texto del PDF: {str(e)}"
        logger.error(error_msg)
        return {"status": "error", "error": str(e)}

    finally:
        # Eliminar archivo temporal si existe
        try:
            if ruta_temp and os.path.exists(ruta_temp):
                os.remove(ruta_temp)
                logger.info(f"Archivo temporal eliminado: {ruta_temp}")
        except Exception as e:
            logger.warning(f"No se pudo eliminar el archivo temporal: {str(e)}")


# ============================================================================
# SECCIÓN 2: PARSING Y ESTRUCTURACIÓN DE DATOS
# ============================================================================
# Tools para convertir texto crudo en datos estructurados
# ============================================================================

def parsear_datos_factura(texto_factura: str) -> dict:
    """
    [ACTIVA] Extrae datos estructurados de una factura desde texto OCR.

    Usa OpenAI para analizar el texto y extraer campos como:
    - SupplierName, SupplierTaxNumber
    - SupplierInvoiceIDByInvcgParty (número de factura)
    - DocumentDate, InvoiceGrossAmount
    - AssignmentReference (código de autorización)
    - Items (lista de productos)

    Args:
        texto_factura: Texto crudo extraído del PDF por OCR

    Returns:
        dict con keys:
            - status: "success" o "error"
            - data: diccionario con datos estructurados (si success)
            - error: mensaje de error (si error)
    """
    try:
        logger.info("Parseando datos de factura desde texto OCR...")
        datos = extraer_datos_factura_desde_texto(texto_factura)

        if datos:
            return {
                "status": "success",
                "data": datos
            }
        else:
            return {
                "status": "error",
                "error": "No se pudieron extraer datos de la factura"
            }

    except Exception as e:
        logger.error(f"Error al parsear datos de factura: {e}")
        return {"status": "error", "error": str(e)}


# ============================================================================
# SECCIÓN 3: VALIDACIÓN SAP
# ============================================================================
# Tools para validar datos contra SAP (proveedores, órdenes de compra)
# ============================================================================

def validar_proveedor_sap(nombre_proveedor: str, nit_proveedor: str = "") -> dict:
    """
    [ACTIVA] Valida y busca un proveedor en SAP S4HANA.

    Estrategias de búsqueda (en orden):
    1. Coincidencia exacta por NIT/Tax Number
    2. Similitud de nombres (>=95%)
    3. Coincidencia de palabras clave
    4. Validación con AI (fallback)

    Args:
        nombre_proveedor: Nombre del proveedor a buscar
        nit_proveedor: NIT/Tax Number del proveedor (opcional pero recomendado)

    Returns:
        dict con keys:
            - status: "success", "not_found" o "error"
            - data: información del proveedor SAP (si success)
            - error: mensaje de error (si error)
    """
    try:
        logger.info(f"Validando proveedor: {nombre_proveedor} (NIT: {nit_proveedor})")

        # Obtener lista de proveedores de SAP
        proveedores_sap = obtener_proveedores_sap()
        if not proveedores_sap:
            return {
                "status": "error",
                "error": "No se pudieron obtener proveedores de SAP"
            }

        # Preparar datos para búsqueda
        factura_datos = {
            "SupplierName": nombre_proveedor,
            "SupplierTaxNumber": nit_proveedor
        }

        # Buscar proveedor
        proveedor_info = buscar_proveedor_en_sap(factura_datos, proveedores_sap)

        if proveedor_info:
            return {
                "status": "success",
                "data": proveedor_info
            }
        else:
            return {
                "status": "not_found",
                "error": f"Proveedor no encontrado en SAP: {nombre_proveedor}"
            }

    except Exception as e:
        logger.error(f"Error al validar proveedor: {e}")
        return {"status": "error", "error": str(e)}


def obtener_ordenes_compra(
    supplier_code: str,
    factura_datos: dict = None,
    tax_code: str = "V0"
) -> dict:
    """
    [ACTIVA] Obtiene y selecciona la mejor orden de compra de un proveedor en SAP.

    Usa selección determinística en dos niveles:
    - Nivel 1: Filtro por Header (status, fecha, moneda)
    - Nivel 2: Scoring por Ítem (precio unitario, cantidad, monto, descripción)

    Args:
        supplier_code: Código SAP del proveedor (ej: "0000001234")
        factura_datos: Datos completos de la factura (del parseo OCR)
        tax_code: Código de impuesto (ej: "V0")

    Returns:
        dict con keys:
            - status: "success", "not_found", "duplicate_requires_intervention" o "error"
            - data: información de la OC seleccionada (si success)
                - selected_purchase_order: ID de la OC
                - selected_purchase_order_item: ítem de la OC
                - needs_migo: bool indicando si requiere entrada de material
                - match_score: puntaje de coincidencia
                - oc_items: lista formateada para construir_json_factura_sap
            - error: mensaje de error (si error/not_found)
    """
    try:
        logger.info(f"Buscando OCs para proveedor: {supplier_code}")

        if not factura_datos:
            factura_datos = {}

        resultado_oc = obtener_ordenes_compra_proveedor(
            factura_datos,
            supplier_code,
            tax_code
        )

        # El resultado ya viene con el formato correcto
        if resultado_oc.get("status") == "success":
            return {
                "status": "success",
                "data": resultado_oc
            }
        elif resultado_oc.get("status") == "duplicate_requires_intervention":
            return {
                "status": "duplicate_requires_intervention",
                "error": resultado_oc.get("error", "Múltiples OCs con score similar"),
                "candidatos": resultado_oc.get("candidatos", [])
            }
        else:
            return {
                "status": resultado_oc.get("status", "not_found"),
                "error": resultado_oc.get("error", f"No se encontraron OCs para el proveedor {supplier_code}")
            }

    except Exception as e:
        logger.error(f"Error al obtener OCs: {e}")
        return {"status": "error", "error": str(e)}

def verificar_entrada_material(
    purchase_order: str = "",
    purchase_order_item: str = "",
    factura_datos: dict = None,
    oc_info: dict = None
) -> dict:
    """
    [ACTIVA] Verifica la entrada de material (MIGO) para una orden de compra.

    Args:
        purchase_order: Número de orden de compra (ej: "4500000098")
        purchase_order_item: Ítem de la OC (opcional, ej: "00010")
        factura_datos: Datos de la factura (para validación de cantidades)
        oc_info: Información de la OC seleccionada (PurchaseOrder, PurchaseOrderItem, Material)

    Returns:
        dict con keys:
            - status: "success", "not_found" o "error"
            - data: información de la entrada de material (si success)
                - reference_document: dict con ReferenceDocument, Year, Item
                - match_score: puntaje de coincidencia
                - cantidad_disponible: cantidad en almacén
                - cantidad_factura: cantidad solicitada
            - error: mensaje de error (si error/not_found)
    """
    try:
        # Preparar oc_info si no se proporcionó completo
        if not oc_info:
            oc_info = {}

        if purchase_order:
            oc_info["PurchaseOrder"] = purchase_order
        if purchase_order_item:
            oc_info["PurchaseOrderItem"] = purchase_order_item

        if not oc_info.get("PurchaseOrder"):
            return {
                "status": "error",
                "error": "No se proporcionó número de orden de compra"
            }

        logger.info(f"Verificando entrada de material para OC: {oc_info.get('PurchaseOrder')}")

        # Preparar factura_datos si no se proporcionó
        if not factura_datos:
            factura_datos = {}

        # Usar la nueva función de verificación
        resultado = verificar_entradas_material(factura_datos, oc_info)

        # Adaptar respuesta al formato esperado por los scripts
        if resultado.get("status") == "success":
            return {
                "status": "success",
                "data": {
                    "reference_document": resultado.get("reference_document", {}),
                    "match_score": resultado.get("match_score", 0),
                    "cantidad_disponible": resultado.get("cantidad_disponible", 0),
                    "cantidad_factura": resultado.get("cantidad_factura", 0),
                    "estado_cantidad": resultado.get("estado_cantidad", "")
                }
            }
        else:
            return {
                "status": resultado.get("status", "error"),
                "error": resultado.get("error", "Error desconocido en verificación MIGO")
            }

    except Exception as e:
        logger.error(f"Error al verificar entrada de material: {e}")
        return {"status": "error", "error": str(e)}


# ============================================================================
# SECCIÓN 4: CONSTRUCCIÓN Y ENVÍO A SAP
# ============================================================================
# Tools para construir payloads y enviar datos a SAP
# ============================================================================

def construir_json_factura(
    factura_datos: dict,
    proveedor_info: dict,
    oc_items: list,
    needs_migo: bool = False,
    reference_document: dict = None
) -> dict:
    """
    [ACTIVA] Construye el JSON de factura en formato SAP.

    Args:
        factura_datos: Datos extraídos de la factura (de parsear_datos_factura)
        proveedor_info: Información del proveedor SAP (de validar_proveedor_sap)
        oc_items: Lista de OCs (de obtener_ordenes_compra)
        needs_migo: Si True, incluye campos ReferenceDocument (requiere MIGO)
        reference_document: Datos del documento de referencia (MIGO) si needs_migo=True

    Returns:
        dict con keys:
            - status: "success" o "error"
            - data: JSON listo para enviar a SAP (si success)
            - error: mensaje de error (si error)
    """
    try:
        logger.info("Construyendo JSON para SAP...")

        factura_json = construir_json_factura_sap(
            factura_datos,
            proveedor_info,
            oc_items,
            needs_migo=needs_migo,
            reference_document=reference_document
        )

        if factura_json:
            return {
                "status": "success",
                "data": factura_json
            }
        else:
            return {
                "status": "error",
                "error": "No se pudo construir el JSON (faltan OCs)"
            }

    except Exception as e:
        logger.error(f"Error al construir JSON: {e}")
        return {"status": "error", "error": str(e)}


def enviar_factura_sap(factura_json: dict) -> dict:
    """
    [ACTIVA] Envía una factura a SAP S4HANA.

    Obtiene token CSRF y envía el JSON de factura.

    Args:
        factura_json: JSON de factura (de construir_json_factura)

    Returns:
        dict con keys:
            - status: "success" o "error"
            - data: respuesta de SAP (si success)
            - error: mensaje de error (si error)
    """
    try:
        logger.info("Enviando factura a SAP...")

        respuesta = enviar_factura_a_sap(factura_json)

        if respuesta:
            return {
                "status": "success",
                "data": respuesta
            }
        else:
            return {
                "status": "error",
                "error": "No se pudo enviar la factura a SAP"
            }

    except Exception as e:
        logger.error(f"Error al enviar factura: {e}")
        return {"status": "error", "error": str(e)}

# ============================================================================
# SECCIÓN 5: Manejo de errores y notificaciones
# ============================================================================
# Tools para enviar correos de notificación en caso de errores críticos
# ============================================================================
def notificar_error_admin(error_: str, cuerpo: str) -> dict:
    """
    [ACTIVA] Envía un correo de notificación al administrador.

    .

    Args:
        

    Returns:
        
    """
    try:
        logger.info("Enviando correo...")

        respuesta = enviar_correo_admin(error_, cuerpo)

        if respuesta:
            return {
                "status": "success",
                "data": respuesta
            }
        else:
            return {
                "status": "error",
                "error": "No se pudo enviar correo"
            }

    except Exception as e:
        logger.error(f"Error al enviar correo: {e}")
        return {"status": "error", "error": str(e)}


# ============================================================================
# ÍNDICE DE TOOLS DISPONIBLES
# ============================================================================
# Resumen rápido para búsqueda:
#
# EXTRACCIÓN:
#   - extraer_texto_pdf(ruta_gcs) -> [ACTIVA]
#
# PARSING:
#   - parsear_datos_factura(texto_factura) -> [ACTIVA]
#
# VALIDACIÓN SAP:
#   - validar_proveedor_sap(nombre, nit) -> [ACTIVA]
#   - obtener_ordenes_compra(supplier_code, descripcion, monto, tax_code) -> [ACTIVA]
#   - verificar_entrada_material(purchase_order, purchase_order_item, factura_datos, oc_info) -> [ACTIVA]
#
# CONSTRUCCIÓN/ENVÍO:
#   - construir_json_factura(factura_datos, proveedor_info, oc_items) -> [ACTIVA]
#   - enviar_factura_sap(factura_json) -> [ACTIVA]
#
# ============================================================================

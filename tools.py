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

from utilities.general import get_transcript_document_cloud_vision
from utilities.image_storage import download_pdf_to_tempfile
from services.sap_operations import (
    extraer_datos_factura_desde_texto,
    obtener_proveedores_sap,
    buscar_proveedor_en_sap,
    obtener_ordenes_compra_proveedor,
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
    2. Similitud de nombres (>=60%)
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
    descripcion_producto: str = "",
    monto_factura: float = 0.0,
    tax_code: str = ""
) -> dict:
    """
    [ACTIVA] Obtiene órdenes de compra de un proveedor en SAP.

    Busca OCs activas para el proveedor y usa AI para seleccionar
    la más apropiada según la descripción del producto.

    Args:
        supplier_code: Código SAP del proveedor (ej: "0000001234")
        descripcion_producto: Descripción del producto en la factura
        monto_factura: Monto total de la factura
        tax_code: Código de impuesto (ej: "V0")

    Returns:
        dict con keys:
            - status: "success", "not_found" o "error"
            - data: lista de OCs seleccionadas (si success)
            - error: mensaje de error (si error/not_found)
    """
    try:
        logger.info(f"Buscando OCs para proveedor: {supplier_code}")

        oc_items = obtener_ordenes_compra_proveedor(
            descripcion_producto,
            monto_factura,
            supplier_code,
            tax_code
        )

        if oc_items:
            return {
                "status": "success",
                "data": oc_items
            }
        else:
            return {
                "status": "not_found",
                "error": f"No se encontraron OCs para el proveedor {supplier_code}"
            }

    except Exception as e:
        logger.error(f"Error al obtener OCs: {e}")
        return {"status": "error", "error": str(e)}


# ============================================================================
# SECCIÓN 4: CONSTRUCCIÓN Y ENVÍO A SAP
# ============================================================================
# Tools para construir payloads y enviar datos a SAP
# ============================================================================

def construir_json_factura(
    factura_datos: dict,
    proveedor_info: dict,
    oc_items: list
) -> dict:
    """
    [ACTIVA] Construye el JSON de factura en formato SAP.

    Args:
        factura_datos: Datos extraídos de la factura (de parsear_datos_factura)
        proveedor_info: Información del proveedor SAP (de validar_proveedor_sap)
        oc_items: Lista de OCs (de obtener_ordenes_compra)

    Returns:
        dict con keys:
            - status: "success" o "error"
            - data: JSON listo para enviar a SAP (si success)
            - error: mensaje de error (si error)
    """
    try:
        logger.info("Construyendo JSON para SAP...")

        factura_json = construir_json_factura_sap(factura_datos, proveedor_info, oc_items)

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
# SECCIÓN 5: FLUJOS COMPLETOS (ORQUESTACIÓN)
# ============================================================================
# Tools que ejecutan flujos completos (múltiples pasos)
# Preferir usar tools individuales para mayor control del agente
# ============================================================================

def procesar_factura_completa(texto_factura: str) -> dict:
    """
    [RESERVA] Procesa una factura completa desde texto OCR hasta carga en SAP.

    NOTA: Esta función ejecuta todo el flujo automáticamente.
    Para mayor control, usar las tools individuales:
    1. parsear_datos_factura()
    2. validar_proveedor_sap()
    3. obtener_ordenes_compra()
    4. construir_json_factura()
    5. enviar_factura_sap()

    Args:
        texto_factura: Texto extraído del PDF (puede ser string o lista)

    Returns:
        dict con keys:
            - success: bool
            - message: mensaje descriptivo
            - data: datos de la factura creada (si success)
            - error: mensaje de error (si falla)
    """
    logger.info("\n" + "=" * 70)
    logger.info("INICIANDO PROCESO COMPLETO DE CARGA DE FACTURA")
    logger.info("=" * 70)

    resultado = {
        'success': False,
        'message': '',
        'data': None,
        'error': None
    }

    try:
        # PASO 1: Extraer datos estructurados
        print("\n" + "=" * 70)
        print("1️⃣ EXTRACCIÓN DE DATOS DE FACTURA")
        print("=" * 70)

        factura_datos = extraer_datos_factura_desde_texto(texto_factura)

        if not factura_datos:
            error_msg = "No se pudieron extraer datos de la factura"
            logger.error(error_msg)
            resultado['error'] = error_msg
            resultado['message'] = error_msg
            return resultado

        # PASO 2: Validar proveedor en SAP
        print("\n" + "=" * 70)
        print("2️⃣ VALIDACIÓN DE PROVEEDOR EN SAP")
        print("=" * 70)

        proveedores_sap = obtener_proveedores_sap()
        if not proveedores_sap:
            error_msg = "No se pudieron obtener proveedores de SAP"
            logger.error(error_msg)
            resultado['error'] = error_msg
            resultado['message'] = error_msg
            return resultado

        proveedor_info = buscar_proveedor_en_sap(factura_datos, proveedores_sap)
        if not proveedor_info:
            error_msg = f"Proveedor no encontrado en SAP: {factura_datos.get('SupplierName')}"
            logger.error(error_msg)
            resultado['error'] = error_msg
            resultado['message'] = error_msg
            return resultado

        # PASO 3: Obtener órdenes de compra
        print("\n" + "=" * 70)
        print("3️⃣ BÚSQUEDA DE ÓRDENES DE COMPRA")
        print("=" * 70)

        supplier_code = proveedor_info.get("Supplier", "")
        if not supplier_code:
            error_msg = "Código de proveedor no disponible"
            logger.error(error_msg)
            resultado['error'] = error_msg
            resultado['message'] = error_msg
            return resultado

        # Extraer descripción de los items
        items = factura_datos.get("Items") or factura_datos.get("items") or []
        if isinstance(items, dict):
            items = [items]

        descripcion_parts = []
        if isinstance(items, list):
            for it in items:
                if not isinstance(it, dict):
                    continue
                for k in ("Description", "Descripcion", "ItemDescription", "description"):
                    v = it.get(k)
                    if v:
                        descripcion_parts.append(str(v).strip())
                        break

        descripcion_factura = "; ".join(descripcion_parts) if descripcion_parts else factura_datos.get("Description") or factura_datos.get("description") or ""
        monto_factura = factura_datos.get("InvoiceGrossAmount", "")
        tax_code = proveedor_info.get("TaxCode", "")

        oc_items = obtener_ordenes_compra_proveedor(
            descripcion_factura, monto_factura, supplier_code, tax_code
        )

        if not oc_items:
            error_msg = f"No se encontraron órdenes de compra para el proveedor {supplier_code}"
            print(f"\n❌ ERROR: {error_msg}")
            logger.error(error_msg)
            resultado['error'] = error_msg
            resultado['message'] = "Factura no tiene OC asociada en SAP"
            return resultado

        # PASO 4: Construir JSON para SAP
        print("\n" + "=" * 70)
        print("4️⃣ CONSTRUCCIÓN DE JSON PARA SAP")
        print("=" * 70)

        factura_json = construir_json_factura_sap(factura_datos, proveedor_info, oc_items)

        if not factura_json:
            error_msg = "No se pudo construir el JSON para SAP"
            logger.error(error_msg)
            resultado['error'] = error_msg
            resultado['message'] = error_msg
            return resultado

        # PASO 5: Enviar a SAP
        print("\n" + "=" * 70)
        print("5️⃣ ENVÍO A SAP")
        print("=" * 70)

        respuesta_sap = enviar_factura_a_sap(factura_json)

        if not respuesta_sap:
            error_msg = "No se pudo enviar la factura a SAP"
            logger.error(error_msg)
            resultado['error'] = error_msg
            resultado['message'] = error_msg
            return resultado

        # ÉXITO
        print("\n" + "=" * 70)
        print("🎉 FACTURA CREADA EXITOSAMENTE EN SAP")
        print("=" * 70)

        resultado['success'] = True
        resultado['message'] = "Factura cargada exitosamente en SAP"
        resultado['data'] = {
            'factura_id': factura_json.get('SupplierInvoiceIDByInvcgParty'),
            'proveedor': proveedor_info.get('SupplierName'),
            'proveedor_codigo': proveedor_info.get('Supplier'),
            'monto': factura_json.get('InvoiceGrossAmount'),
            'codigo_autorizacion': factura_json.get('AssignmentReference'),
            'oc_count': len(oc_items),
            'respuesta_sap': respuesta_sap,
            'json_final': factura_json
        }

        return resultado

    except Exception as e:
        error_msg = f"Error inesperado en el procesamiento: {str(e)}"
        print(f"\n❌ ERROR: {error_msg}")
        logger.error(error_msg)
        logger.exception(e)

        resultado['error'] = error_msg
        resultado['message'] = "Error en el procesamiento de la factura"

        return resultado


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
#
# CONSTRUCCIÓN/ENVÍO:
#   - construir_json_factura(factura_datos, proveedor_info, oc_items) -> [ACTIVA]
#   - enviar_factura_sap(factura_json) -> [ACTIVA]
#
# FLUJOS COMPLETOS:
#   - procesar_factura_completa(texto_factura) -> [RESERVA]
# ============================================================================

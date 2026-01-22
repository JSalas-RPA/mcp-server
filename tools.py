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
    obtener_entradas_material_por_oc,
    validar_y_seleccionar_entrada_material,
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
    purchase_order: str,
    purchase_order_item: str = "",
    factura_datos: dict = None,
    oc_info: dict = None
) -> dict:
    """
    [ACTIVA] Verifica la entrada de material (MIGO) para una orden de compra.

    Busca las entradas de material asociadas a la OC y selecciona
    la más apropiada para la factura.

    Args:
        purchase_order: Número de orden de compra (ej: "4500000098")
        purchase_order_item: Ítem de la OC (opcional, ej: "00010")
        factura_datos: Datos de la factura (opcional, para validación adicional)
        oc_info: Información de la OC seleccionada (opcional)

    Returns:
        dict con keys:
            - status: "success", "not_found" o "error"
            - data: información de la entrada de material (si success)
                - entradas_encontradas: lista de todas las entradas
                - entrada_seleccionada: entrada seleccionada para la factura
            - error: mensaje de error (si error/not_found)
    """
    try:
        logger.info(f"Verificando entrada de material para OC: {purchase_order}")

        if not purchase_order:
            return {
                "status": "error",
                "error": "No se proporcionó número de orden de compra"
            }

        # Obtener entradas de material de SAP
        entradas = obtener_entradas_material_por_oc(
            purchase_order,
            purchase_order_item
        )

        if not entradas:
            return {
                "status": "not_found",
                "error": f"No se encontraron entradas de material para OC {purchase_order}"
            }

        # Preparar oc_info si no se proporcionó
        if not oc_info:
            oc_info = {
                "PurchaseOrder": purchase_order,
                "PurchaseOrderItem": purchase_order_item or ""
            }

        # Preparar factura_datos si no se proporcionó
        if not factura_datos:
            factura_datos = {}

        # Seleccionar la entrada más apropiada
        entrada_seleccionada = validar_y_seleccionar_entrada_material(
            factura_datos,
            oc_info,
            entradas
        )

        return {
            "status": "success",
            "data": {
                "entradas_encontradas": entradas,
                "total_entradas": len(entradas),
                "entrada_seleccionada": entrada_seleccionada
            }
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

        # Obtener tax_code del proveedor
        tax_code = proveedor_info.get("TaxCode", "V0")

        # Llamar a la nueva función de selección de OC (determinística)
        resultado_oc = obtener_ordenes_compra_proveedor(
            factura_datos, supplier_code, tax_code
        )

        # Verificar resultado de la selección de OC
        if resultado_oc.get("status") != "success":
            if resultado_oc.get("status") == "duplicate_requires_intervention":
                error_msg = "Múltiples OCs con score similar, requiere intervención manual"
                resultado['error'] = error_msg
                resultado['message'] = error_msg
                resultado['candidatos_oc'] = resultado_oc.get("candidatos", [])
            else:
                error_msg = resultado_oc.get("error", f"No se encontraron OCs para el proveedor {supplier_code}")
            print(f"\n❌ ERROR: {error_msg}")
            logger.error(error_msg)
            resultado['error'] = error_msg
            resultado['message'] = "Factura no tiene OC asociada en SAP"
            return resultado

        # Extraer datos de la OC seleccionada
        oc_items = resultado_oc.get("oc_items", [])
        needs_migo = resultado_oc.get("needs_migo", False)
        match_score = resultado_oc.get("match_score", 0)
        selected_oc = resultado_oc.get("selected_purchase_order", "")
        selected_oc_item = resultado_oc.get("selected_purchase_order_item", "")

        print(f"\n  📊 RESULTADO SELECCIÓN OC:")
        print(f"     • OC Seleccionada: {selected_oc} - Item {selected_oc_item}")
        print(f"     • Score: {match_score:.1f}/100")
        print(f"     • Requiere MIGO: {'Sí' if needs_migo else 'No'}")

        # PASO 3.5: Si needs_migo, obtener entrada de material
        reference_document = None
        if needs_migo:
            print("\n" + "=" * 70)
            print("3.5️⃣ VERIFICACIÓN DE ENTRADA DE MATERIAL (MIGO)")
            print("=" * 70)

            from services.sap_operations import obtener_entradas_material_por_oc, validar_y_seleccionar_entrada_material

            entradas = obtener_entradas_material_por_oc(selected_oc, selected_oc_item)
            if entradas:
                reference_document = validar_y_seleccionar_entrada_material(
                    factura_datos,
                    {"PurchaseOrder": selected_oc, "PurchaseOrderItem": selected_oc_item},
                    entradas
                )
                if not reference_document:
                    error_msg = f"OC {selected_oc} requiere MIGO pero no se encontró entrada de material"
                    print(f"\n❌ ERROR: {error_msg}")
                    logger.error(error_msg)
                    resultado['error'] = error_msg
                    resultado['message'] = "Factura requiere entrada de material (MIGO) no encontrada"
                    return resultado
            else:
                error_msg = f"OC {selected_oc} requiere MIGO pero no hay entradas de material"
                print(f"\n❌ ERROR: {error_msg}")
                logger.error(error_msg)
                resultado['error'] = error_msg
                resultado['message'] = "Factura requiere entrada de material (MIGO) no encontrada"
                return resultado

        # PASO 4: Construir JSON para SAP
        print("\n" + "=" * 70)
        print("4️⃣ CONSTRUCCIÓN DE JSON PARA SAP")
        print("=" * 70)

        factura_json = construir_json_factura_sap(
            factura_datos,
            proveedor_info,
            oc_items,
            needs_migo=needs_migo,
            reference_document=reference_document
        )

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
#   - verificar_entrada_material(purchase_order, purchase_order_item, factura_datos, oc_info) -> [ACTIVA]
#
# CONSTRUCCIÓN/ENVÍO:
#   - construir_json_factura(factura_datos, proveedor_info, oc_items) -> [ACTIVA]
#   - enviar_factura_sap(factura_json) -> [ACTIVA]
#
# FLUJOS COMPLETOS:
#   - procesar_factura_completa(texto_factura) -> [RESERVA]
# ============================================================================

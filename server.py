# server.py - Servidor MCP Dsuite
# ============================================================================
# Servidor de Tools MCP para automatización de facturas SAP S4HANA
#
# Tools ACTIVAS (registradas aquí):
#   - extraer_texto: Extrae texto de PDF via OCR
#   - parsear_factura: Estructura datos desde texto OCR
#   - validar_proveedor: Valida proveedor en SAP
#   - verificar_factura_duplicada: Verifica si factura ya tiene MIRO
#   - buscar_ordenes_compra: Obtiene OCs de un proveedor
#   - verificar_migo: Verifica entrada de material (MIGO) para OC
#   - construir_json: Construye JSON para SAP
#   - enviar_a_sap: Envía factura a SAP
#
# Para agregar nuevas tools:
#   1. Crear la función en tools.py
#   2. Importarla aquí
#   3. Registrarla con @mcp.tool()
# ============================================================================

import asyncio
import json
import logging
import os

from fastmcp import FastMCP

from utilities.ocr import get_transcript_document_cloud_vision, get_transcript_document
from utilities.file_storage import download_pdf_to_tempfile
from utilities.email_client import send_email
from tools_sap_services.sap_operations import (
    extraer_datos_factura_desde_texto,
    obtener_proveedores_sap,
    buscar_proveedor_en_sap,
    obtener_ordenes_compra_proveedor,
    verificar_entradas_material,
    verificar_entradas_material_multi,
    construir_json_factura_sap,
    enviar_factura_a_sap,
)
from tools_sap_services.sap_api import buscar_factura_existente

logger = logging.getLogger(__name__)
logging.basicConfig(format="[%(levelname)s]: %(message)s", level=logging.INFO)

# Crear servidor MCP
mcp = FastMCP("MCP Server S4HANA Tools")


# ============================================================================
# TOOLS DE EXTRACCIÓN
# ============================================================================

@mcp.tool()
def extraer_texto(ruta_gcs: str) -> dict:
    """
    Extrae texto de un PDF usando OCR (Cloud Vision).

    Args:
        ruta_gcs: Ruta al PDF (gs://, https://, local o blob relativo)

    Returns:
        dict con status, data (texto) o error
    """
    ruta_temp = None
    try:
        logger.info(f"Iniciando extracción de texto desde: {ruta_gcs}")
        # Descargar PDF a archivo temporal
        ruta_temp = download_pdf_to_tempfile(ruta_gcs)
        logger.info(f"Archivo temporal descargado: {ruta_temp}")
        # OCR con Cloud Vision
        logger.info("Extrayendo texto con Cloud Vision")
        texto_factura = get_transcript_document(ruta_temp)
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
        try:
            if ruta_temp and os.path.exists(ruta_temp):
                os.remove(ruta_temp)
                logger.info(f"Archivo temporal eliminado: {ruta_temp}")
        except Exception as e:
            logger.warning(f"No se pudo eliminar el archivo temporal: {str(e)}")

# ============================================================================
# TOOLS DE PARSING
# ============================================================================

@mcp.tool()
def parsear_factura(texto_factura: str) -> dict:
    """
    Extrae datos estructurados de una factura desde texto OCR.

    Args:
        texto_factura: Texto crudo extraído del PDF

    Returns:
        dict con status, data (campos estructurados) o error
    """
    logger.info(f"Tool 'parsear_factura' llamada")
    resultado = extraer_datos_factura_desde_texto(texto_factura)
    logger.info(f"Resultado: {resultado.get('SupplierInvoiceIDByInvcgParty')}")
    return resultado


# ============================================================================
# TOOLS DE VALIDACIÓN SAP
# ============================================================================

@mcp.tool()
def validar_proveedor(factura_datos: dict) -> dict:
    """
    Valida y busca un proveedor en SAP S4HANA.

    Args:
        factura_datos: Datos estructurados de la factura (del parseo OCR)
        nit_proveedor: NIT/Tax Number (opcional pero recomendado)

    Returns:
        dict con status (success/not_found/error), data o error
    """
    logger.info(f"Tool 'validar_proveedor' llamada con factura_datos={factura_datos}")
    proveedores_sap = obtener_proveedores_sap()
    if not proveedores_sap:
        logger.error("No se pudieron obtener proveedores de SAP")
        return {
            "status": "error",
            "error": "No se pudieron obtener proveedores de SAP"
        }
    resultado = buscar_proveedor_en_sap(factura_datos, proveedores_sap=proveedores_sap)
    logger.info(f"Resultado: {resultado.get('supplier')}")
    return resultado


@mcp.tool()
def verificar_factura_duplicada(invoice_id: str, supplier_code: str) -> dict:
    """
    Verifica si ya existe un MIRO (Supplier Invoice) en SAP con el mismo
    numero de factura y proveedor, para evitar duplicados.

    Args:
        invoice_id: Numero de factura del proveedor (SupplierInvoiceIDByInvcgParty)
        supplier_code: Codigo del proveedor en SAP (InvoicingParty)

    Returns:
        dict con status (exists/not_found/error) y data del MIRO existente si aplica
    """
    logger.info(f"Tool 'verificar_factura_duplicada' llamada con invoice_id={invoice_id}, supplier_code={supplier_code}")
    resultado = buscar_factura_existente(invoice_id, supplier_code)
    logger.info(f"Resultado: {resultado.get('status')}")
    return resultado


@mcp.tool()
def buscar_ordenes_compra(factura_datos, supplier_code) -> dict:
    """
    Obtiene órdenes de compra de un proveedor en SAP.

    Args:
        supplier_code: Código SAP del proveedor (ej: "0000001234")
        factura_datos: Datos completos de la factura (del parseo OCR)
        tax_code: Código de impuesto (ej: "V0")

    Returns:
        dict con status (success/not_found/duplicate_requires_intervention/error), data (OC seleccionada) o error
    """
    logger.info(f"Tool 'buscar_ordenes_compra' llamada con supplier_code={supplier_code}")
    resultado = obtener_ordenes_compra_proveedor(factura_datos, supplier_code)
    logger.info(f"Resultado: {resultado.get('status')}")
    return resultado


@mcp.tool()
def verificar_migo(
    factura_datos: dict = None,
    oc_info: dict = None,
    oc_items: list = None
) -> dict:
    """
    Verifica la entrada de material (MIGO) para una orden de compra.

    Soporta dos modos:
    - Single: pasar oc_info con un solo item de OC
    - Multi-item: pasar oc_items con la lista de items de OC (cuando la factura tiene múltiples items)

    Args:
        factura_datos: Datos de la factura
        oc_info: Información de la OC seleccionada (modo single)
        oc_items: Lista de items de OC (modo multi-item, tiene prioridad sobre oc_info)

    Returns:
        dict con status (success/not_found/error), reference_document(s), match_score, etc.
    """
    if oc_items and len(oc_items) > 1:
        logger.info(f"Tool 'verificar_migo' llamada en modo MULTI-ITEM ({len(oc_items)} items)")
        resultado = verificar_entradas_material_multi(factura_datos, oc_items)
    else:
        # Modo single: usar oc_info directamente, o extraer del primer oc_items
        if not oc_info and oc_items:
            oc_info = {
                "PurchaseOrder": oc_items[0].get("PurchaseOrder", ""),
                "PurchaseOrderItem": oc_items[0].get("PurchaseOrderItem", ""),
                "Material": oc_items[0].get("Material", "")
            }
        logger.info(f"Tool 'verificar_migo' llamada con purchase_order={oc_info.get('PurchaseOrder') if oc_info else 'N/A'}")
        resultado = verificar_entradas_material(factura_datos, oc_info)

    logger.info(f"Resultado: {resultado.get('status')}")
    return resultado


# ============================================================================
# TOOLS DE CONSTRUCCIÓN Y ENVÍO
# ============================================================================

@mcp.tool()
def construir_json(
    factura_datos: dict,
    proveedor_info: dict,
    oc_items: list,
    needs_migo: bool = False,
    reference_document: dict | list = None
) -> dict:
    """
    Construye el JSON de factura en formato SAP.

    Args:
        factura_datos: Datos extraídos de la factura
        proveedor_info: Información del proveedor SAP
        oc_items: Lista de órdenes de compra
        needs_migo: Si True, incluye campos ReferenceDocument (requiere MIGO)
        reference_document: Datos del documento de referencia (MIGO) si needs_migo=True.
            Puede ser un dict (single) o lista de dicts (multi-item).

    Returns:
        dict con status, data (JSON para SAP) o error
    """
    logger.info(f"Tool 'construir_json' llamada")
    resultado = construir_json_factura_sap(factura_datos, proveedor_info, oc_items, needs_migo, reference_document)
    logger.info(f"Json construido: {json.dumps(resultado, indent=2, ensure_ascii=False)}")
    return resultado


@mcp.tool()
def enviar_a_sap(factura_json: dict) -> dict:
    """
    Envía una factura a SAP S4HANA.

    Args:
        factura_json: JSON de factura construido

    Returns:
        list true/false y mensaje
    """
    logger.info(f"Tool 'enviar_a_sap' llamada")
    resultado = enviar_factura_a_sap(factura_json)
    logger.info(f"Resultado: {resultado.get('d', {}).get('SupplierInvoice')}")
    return resultado

@mcp.tool()
def enviar_correo(destinatario: str, asunto: str, cuerpo: str) -> list:
    """
    Envía un correo electrónico.

    Args:
        destinatario: Dirección de correo del destinatario
        asunto: Asunto del correo
        cuerpo: Cuerpo del correo

    Returns:
        dict con status (success/error) y mensaje
    """
    logger.info(f"Tool 'enviar_correo' llamada")
    resultado = send_email(destinatario, asunto, cuerpo)
    logger.info(f"Resultado: {resultado}")
    return resultado

# ============================================================================
# EJECUCIÓN DEL SERVIDOR
# ============================================================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    logger.info(f"MCP server iniciando en puerto {port}")
    logger.info("Tools activas: extraer_texto, parsear_factura, validar_proveedor, verificar_factura_duplicada, buscar_ordenes_compra, verificar_migo, construir_json, enviar_a_sap")
    asyncio.run(
        mcp.run_async(
            transport="sse", #http/sse
            host="0.0.0.0",
            port=port
        )
    )

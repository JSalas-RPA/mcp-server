# server.py - Servidor MCP Dsuite
# ============================================================================
# Servidor de Tools MCP para automatización de facturas SAP S4HANA
#
# Tools ACTIVAS (registradas aquí):
#   - extraer_texto: Extrae texto de PDF via OCR
#   - parsear_factura: Estructura datos desde texto OCR
#   - validar_proveedor: Valida proveedor en SAP
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
import logging
import os

from fastmcp import FastMCP
from tools import (
    extraer_texto_pdf,
    parsear_datos_factura,
    validar_proveedor_sap,
    obtener_ordenes_compra,
    verificar_entrada_material,
    construir_json_factura,
    enviar_factura_sap,
)

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
    logger.info(f"Tool 'extraer_texto' llamada con ruta_gcs={ruta_gcs}")
    resultado = extraer_texto_pdf(ruta_gcs)
    logger.info(f"Resultado: {resultado.get('status')}")
    return resultado


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
    resultado = parsear_datos_factura(texto_factura)
    logger.info(f"Resultado: {resultado.get('status')}")
    return resultado


# ============================================================================
# TOOLS DE VALIDACIÓN SAP
# ============================================================================

@mcp.tool()
def validar_proveedor(nombre_proveedor: str, nit_proveedor: str = "") -> dict:
    """
    Valida y busca un proveedor en SAP S4HANA.

    Args:
        nombre_proveedor: Nombre del proveedor
        nit_proveedor: NIT/Tax Number (opcional pero recomendado)

    Returns:
        dict con status (success/not_found/error), data o error
    """
    logger.info(f"Tool 'validar_proveedor' llamada con nombre={nombre_proveedor}, nit={nit_proveedor}")
    resultado = validar_proveedor_sap(nombre_proveedor, nit_proveedor)
    logger.info(f"Resultado: {resultado.get('status')}")
    return resultado


@mcp.tool()
def buscar_ordenes_compra(
    supplier_code: str,
    descripcion_producto: str = "",
    monto_factura: float = 0.0,
    tax_code: str = ""
) -> dict:
    """
    Obtiene órdenes de compra de un proveedor en SAP.

    Args:
        supplier_code: Código SAP del proveedor (ej: "0000001234")
        descripcion_producto: Descripción del producto en la factura
        monto_factura: Monto total de la factura
        tax_code: Código de impuesto (ej: "V0")

    Returns:
        dict con status (success/not_found/error), data (lista OCs) o error
    """
    logger.info(f"Tool 'buscar_ordenes_compra' llamada con supplier_code={supplier_code}")
    resultado = obtener_ordenes_compra(supplier_code, descripcion_producto, monto_factura, tax_code)
    logger.info(f"Resultado: {resultado.get('status')}")
    return resultado


@mcp.tool()
def verificar_migo(
    purchase_order: str,
    purchase_order_item: str = "",
    factura_datos: dict = None,
    oc_info: dict = None
) -> dict:
    """
    Verifica la entrada de material (MIGO) para una orden de compra.

    Args:
        purchase_order: Número de orden de compra (ej: "4500000098")
        purchase_order_item: Ítem de la OC (opcional)
        factura_datos: Datos de la factura (opcional)
        oc_info: Información de la OC seleccionada (opcional)

    Returns:
        dict con status (success/not_found/error), data (entradas de material) o error
    """
    logger.info(f"Tool 'verificar_migo' llamada con purchase_order={purchase_order}")
    resultado = verificar_entrada_material(purchase_order, purchase_order_item, factura_datos, oc_info)
    logger.info(f"Resultado: {resultado.get('status')}")
    return resultado


# ============================================================================
# TOOLS DE CONSTRUCCIÓN Y ENVÍO
# ============================================================================

@mcp.tool()
def construir_json(factura_datos: dict, proveedor_info: dict, oc_items: list) -> dict:
    """
    Construye el JSON de factura en formato SAP.

    Args:
        factura_datos: Datos extraídos de la factura
        proveedor_info: Información del proveedor SAP
        oc_items: Lista de órdenes de compra

    Returns:
        dict con status, data (JSON para SAP) o error
    """
    logger.info(f"Tool 'construir_json' llamada")
    resultado = construir_json_factura(factura_datos, proveedor_info, oc_items)
    logger.info(f"Resultado: {resultado.get('status')}")
    return resultado


@mcp.tool()
def enviar_a_sap(factura_json: dict) -> dict:
    """
    Envía una factura a SAP S4HANA.

    Args:
        factura_json: JSON de factura construido

    Returns:
        dict con status, data (respuesta SAP) o error
    """
    logger.info(f"Tool 'enviar_a_sap' llamada")
    resultado = enviar_factura_sap(factura_json)
    logger.info(f"Resultado: {resultado.get('status')}")
    return resultado


# ============================================================================
# EJECUCIÓN DEL SERVIDOR
# ============================================================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    logger.info(f"MCP server iniciando en puerto {port}")
    logger.info("Tools activas: extraer_texto, parsear_factura, validar_proveedor, buscar_ordenes_compra, verificar_migo, construir_json, enviar_a_sap")
    asyncio.run(
        mcp.run_async(
            transport="streamable-http",
            host="0.0.0.0",
            port=port
        )
    )

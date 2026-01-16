# server.py - Servicio A: Servidor de Tools/MCP

import asyncio
import logging
import os
import json
from fastmcp import FastMCP
from tool import extraer_texto_pdf, procesar_factura_completa

logger = logging.getLogger(__name__)
logging.basicConfig(format="[%(levelname)s]: %(message)s", level=logging.INFO)

# Crear servidor MCP
mcp = FastMCP("MCP Server S4HANA Tools")

# ------------------------------
# 1.0 TOOL: Extraer texto de un PDF
# ------------------------------
@mcp.tool()
def extraer_texto(ruta_gcs: str) -> dict:
    logger.info(f"Tool: 'extraer_texto_factura' called with ruta_gcs={ruta_gcs}")
    resultado = extraer_texto_pdf(ruta_gcs)
    logger.info(f"Resultado: {resultado}")
    return resultado

# ------------------------------
# 2.0 TOOL: Procesar factura completa
# ------------------------------
@mcp.tool()
def cargar_factura_a_sap(texto_factura: list) -> dict:
    """
    Tool que procesa y carga una factura a SAP a partir del texto extraído del PDF.
    """
    logger.info(f"Tool: 'cargar_factura_a_sap' called with texto_factura of length={len(texto_factura)}")
    resultado = procesar_factura_completa(texto_factura)
    logger.info(f"Resultado: {resultado}")
    return resultado


# ------------------------------
# Ejecución del servidor MCP
# ------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    logger.info(f"MCP server started on port {port}")
    asyncio.run(
        mcp.run_async(
            transport="streamable-http",
            host="0.0.0.0",
            port=port
        )
    )
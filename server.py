# server.py - Servicio A: Servidor de Tools/MCP

import asyncio
import logging
import os
from fastmcp import FastMCP
from tool import validar_factura_tool, enviar_factura_a_sap_tool
from utilities.image_storage import upload_image_to_gcs

logger = logging.getLogger(__name__)
logging.basicConfig(format="[%(levelname)s]: %(message)s", level=logging.INFO)

# Crear servidor MCP
mcp = FastMCP("MCP Server S4HANA Tools")

# ------------------------------
# 1. TOOL: Subir PDF desde EasyContact a GCS
# ------------------------------
@mcp.tool()
def subir_pdf_easycontact(user_email: str, image_url: str) -> str:
    url = upload_image_to_gcs(user_email, image_url)
    if url:
        return f"Archivo subido correctamente a GCS: {url}"
    else:
        return "Error al subir el archivo."


# ------------------------------
# 2. TOOL: Validar Factura
# ------------------------------
@mcp.tool()
def validar_factura(rutas_bucket: list[str]) -> dict:
    logger.info(f"Tool: 'validar_factura' called with rutas_bucket={rutas_bucket}")
    resultado = validar_factura_tool(rutas_bucket)
    logger.info(f"Resultado: {resultado}")
    return resultado


# ------------------------------
# 3. TOOL: Enviar Factura a SAP S/4HANA
# ------------------------------
@mcp.tool()
def enviar_factura_a_sap(datos_factura: dict, correo_remitente: str) -> dict:
    logger.info(f"Tool: 'enviar_factura_a_sap' llamada para el correo={correo_remitente}")
    resultado_sap = enviar_factura_a_sap_tool(datos_factura, correo_remitente)
    return resultado_sap



# ------------------------------
# 4. TOOL: Tool de prueba para testing
# ------------------------------
@mcp.tool()
def tool_prueba(nombre: str) -> str:
    """
    Tool de prueba que devuelve un mensaje simple.
    
    Parámetro:
        nombre: nombre de prueba
    Retorna:
        string con saludo
    """
    return f"Hola {nombre}, esta es una respuesta de prueba desde MCP Server!"



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

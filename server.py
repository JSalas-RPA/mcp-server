# server.py - Servicio A: Servidor de Tools/MCP

import asyncio
import logging
import os
from fastmcp import FastMCP
from tool import enviar_factura_a_sap_service, validar_factura_tool, enviar_factura_a_sap_tool
from utilities.image_storage import upload_image_to_gcs
import json
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
with open("factura_json.json", "r", encoding="utf-8") as f:
    factura_json = json.load(f)

if "d" in factura_json:
    factura_json = factura_json["d"]
@mcp.tool()
def tool_prueba(nombre: str) -> str:
    """
    Tool de prueba que devuelve un mensaje simple.
    
    Parámetro:
        nombre: nombre de prueba
    Retorna:
        string con saludo
    """
    respuesta_sap = enviar_factura_a_sap_service(factura_json)
    if not respuesta_sap:
        return {"status": "error", "mensaje": "No se pudo crear la factura en SAP"}

    # Acceder al objeto 'd' donde realmente están los datos
    datos = respuesta_sap.get("d", {})

    invoice_id = datos.get("SupplierInvoice")
    fiscal_year = datos.get("FiscalYear")
    internal_id = datos.get("SupplierInvoiceIDByInvcgParty")

    resultado = {
        "status": "success",
        "enviado_por": "andy",
        "invoice_id": invoice_id,
        "fiscal_year": fiscal_year,
        "internal_id": internal_id,
    }

    if debug:
        print("Invoice ID:", invoice_id)
        print("Fiscal Year:", fiscal_year)
        print("Internal ID:", internal_id)

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

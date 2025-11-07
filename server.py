import asyncio
import logging
import os
from fastmcp import FastMCP

# Importar tu tool de facturas
from tool import validar_factura_tool, enviar_factura_a_sheets_tool

logger = logging.getLogger(__name__)
logging.basicConfig(format="[%(levelname)s]: %(message)s", level=logging.INFO)

# Crear servidor MCP
mcp = FastMCP("MCP Server on Cloud Run")

# ------------------------------
# Tool MCP: validar_factura
# ------------------------------

@mcp.tool()
def validar_factura(rutas_bucket: list[str]) -> dict:
    """
    Valida facturas desde Google Cloud Storage.
    
    Parámetro:
        rutas_bucket: lista de nombres de blobs en GCS.
    
    Devuelve:
        dict con resultados y mensaje descriptivo.
    """
    logger.info(f">>> 🛠️ Tool: 'validar_factura' called with rutas_bucket={rutas_bucket}")
    resultado = validar_factura_tool(rutas_bucket)
    logger.info(f">>> 🛠️ Resultado: {resultado}")
    return resultado

@mcp.tool()
def subir_pdf_easycontact(user_email: str, image_url: str) -> str:
    """
    Sube la factura desde el link de easycontact a Google cloud storage.
    
    Parámetro:
        user_email: email del usuario que envía el mensaje.
        image_url: url del archivo adjunto en easycontact(puede ser pdf, imagen, doc, etc.) 
    
    Devuelve:
        Confirmación de subida de archivo.
    """
    url = upload_file_base64_to_gcs(user_email, file_base64)
    if url:
        return f"Archivo subido correctamente: {url}"
    else:
        return "Error al subir el archivo."

@mcp.tool()
def enviar_factura(factura: dict, correo: str) -> dict:
    """
    envía la factura a sheets para ser registrada, solo cuando es válida.

    Parámetros:
        factura: dict con todos los datos de la factura.
        correo: el correo del remitente.

    Devuelve:
        dict con status y mensaje de la operación.
    """
    logger.info(f">>> 🛠️ Tool: 'enviar_factura' called with factura={factura} correo={correo}")
    resultado = enviar_factura_a_sheets_tool(factura, correo)
    logger.info(f">>> 🛠️ Resultado: {resultado}")
    return resultado


# ------------------------------
# Run server MCP
# ------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 7000))
    logger.info(f"🚀 MCP server started on port {port}")
    asyncio.run(
        mcp.run_async(
            transport="streamable-http",
            host="0.0.0.0",
            port=port
        )
    )


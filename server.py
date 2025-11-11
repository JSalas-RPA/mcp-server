import asyncio
import logging
import os
import requests
from fastmcp import FastMCP
from datetime import datetime
# Importar tu tool de facturas
from tool import validar_factura_tool, enviar_factura_a_sheets_tool
from utilities.image_storage import upload_image_to_gcs

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
def enviar_factura_a_sheets(factura: dict, correo_remitente: str) -> dict:
    """
    Envía los datos de una factura a Google Sheets a través del Apps Script.

    Parámetros:
        factura: dict con los datos validados de la factura.
        correo_remitente: correo que realizó la consulta.

    Devuelve:
        dict con el resultado de la operación.
    """
    logger.info(f">>> 🧾 Tool: 'enviar_factura_a_sheets' llamada con correo={correo_remitente}")
    
    # URL del Apps Script desplegado (reemplaza con la tuya)
    SCRIPT_URL = os.getenv("APPS_SCRIPT_URL", "https://script.google.com/macros/s/TU_DEPLOY_ID/exec")

    # Añadimos los campos adicionales
    factura["correo_remitente"] = correo_remitente
    factura["fecha_hora_consulta"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Enviamos la solicitud
    try:
        response = requests.post(SCRIPT_URL, json=factura, timeout=10)
        if response.status_code == 200:
            logger.info("✅ Datos enviados correctamente a Google Sheets.")
            return {"success": True, "status": 200, "response": response.text}
        else:
            logger.error(f"❌ Error al enviar a Sheets: {response.text}")
            return {"success": False, "status": response.status_code, "error": response.text}
    except Exception as e:
        logger.error(f"⚠️ Excepción al enviar factura: {e}")
        return {"success": False, "error": str(e)}


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
    url = upload_image_to_gcs(user_email, image_url)
    if url:
        return f"Archivo subido correctamente a GCS: {url}"
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


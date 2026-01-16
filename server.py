# server.py - Servicio A: Servidor de Tools/MCP

import asyncio
import logging
import os
from fastmcp import FastMCP
#from tool import enviar_factura_a_sap_service, extraer_datos_factura, enviar_factura_a_sap_tool, extraer_texto_pdf, procesar_factura_completa
from tool import extraer_texto_pdf, procesar_factura_completa
import json
logger = logging.getLogger(__name__)
logging.basicConfig(format="[%(levelname)s]: %(message)s", level=logging.INFO)



# Crear servidor MCP
mcp = FastMCP("MCP Server S4HANA Tools")

"""
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
# 2.5 TOOL: Extraer datos de factura
# ------------------------------
@mcp.tool()
def extraer_datos(ruta_gcs: str) -> dict:
    logger.info(f"Tool: 'extraer_datos_factura' called with ruta_gcs={ruta_gcs}")
    resultado = extraer_datos_factura(ruta_gcs)
    logger.info(f"Resultado: {resultado}")
    return resultado


# ------------------------------
# 3. TOOL: Procesar Factura Json a SAP
# ------------------------------

@mcp.tool()
def enviar_factura_a_sap(datos_factura: dict, correo_remitente: str) -> dict:
    logger.info(f"Tool: 'enviar_factura_a_sap' llamada para el correo={correo_remitente}")
    resultado_sap = enviar_factura_a_sap_tool(datos_factura, correo_remitente)
    return resultado_sap

# ------------------------------
# 4. TOOL: Cargar a SAP
# ------------------------------
# ============================================================
# JSON ORIGINAL DE FACTURA (tal como lo recibes o lo defines)
# ============================================================

factura_json ={
  "d": {
    "CompanyCode": "1000",
    "DocumentDate": "2025-12-19T14:30:00",
    "PostingDate": "2025-12-19T14:30:00",
    "SupplierInvoiceIDByInvcgParty": "6057461",
    "InvoicingParty": "1000120",
    "DocumentCurrency": "BOB",
    "InvoiceGrossAmount": "2500",
    "DueCalculationBaseDate": "2025-12-19T14:30:00",
    "TaxIsCalculatedAutomatically": True,
    "TaxDeterminationDate": "2025-12-19T14:30:00",
    "SupplierInvoiceStatus": "B",
    "AssignmentReference":"457C61867FDA31",
    "to_SuplrInvcItemPurOrdRef": {
      "results": [
        {
          "SupplierInvoiceItem": "00001",
          "PurchaseOrder": "4500000000",
          "PurchaseOrderItem": "00010",
          "DocumentCurrency": "BOB",
          "QuantityInPurchaseOrderUnit": "1.000",
          "PurchaseOrderQuantityUnit": "EA",
          "SupplierInvoiceItemAmount": "2500",
          "TaxCode": "V0"
        }
      ]
    }
  }
}
 
# ============================================================
# LIMPIEZA — NO ENVIAMOS NUNCA UN JSON CON "d" DOBLE
# ============================================================

if "d" in factura_json:
    factura_json = factura_json["d"]   # <-- JSON limpio para SAP

# ============================================================
# TOOL FINAL (NO SE MODIFICA NADA INTERNO)
# ============================================================

@mcp.tool()
def tool_prueba(nombre: str) -> dict:
    
    #Tool de prueba que envía la factura a SAP y retorna el resultado.
    
    logger.info(f"FACTURA RECIBIDA EN LA FUNCIÓN: {type(factura_json)}")

    # Enviar JSON limpio a SAP
    respuesta_sap = enviar_factura_a_sap_service(factura_json)

    if not respuesta_sap:
        logger.error("No se pudo crear la factura en SAP")
        return {"status": "error", "mensaje": "No se pudo crear la factura en SAP"}

    # SAP devuelve la respuesta dentro de "d"
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

    # Logging de los valores devueltos
    logger.info(f"Invoice ID: {invoice_id}, Fiscal Year: {fiscal_year}, Internal ID: {internal_id}")

    return resultado
"""

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
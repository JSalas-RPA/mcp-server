import asyncio
import logging
import os
from fastmcp import FastMCP

# Importar tu tool de facturas
from tool import validar_factura_tool

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


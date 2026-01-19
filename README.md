# Project Overview

MCP Server for SAP S4HANA invoice automation. This is a FastMCP-based server that provides tools for processing supplier invoices: extracting data from PDFs via OCR, validating suppliers in SAP, matching purchase orders, and submitting invoices to SAP S4HANA.

## Commands

### Run the MCP Server
```bash
python server.py
```
Server runs on port 8080 by default (configurable via `PORT` env var).

### Run Invoice Processing Flow (CLI)
```bash
# Process a PDF and optionally send to SAP
python -m scripts.flujo_completo <ruta_pdf> [--enviar]

# Examples:
python -m scripts.flujo_completo /ruta/factura.pdf
python -m scripts.flujo_completo gs://bucket/factura.pdf
python -m scripts.flujo_completo factura.pdf --enviar  # Actually sends to SAP
```

### Docker Build
```bash
docker build -t mcp-server .
```

### Cloud Build
```bash
gcloud builds submit --config=cloudbuild.yaml
```

## Architecture

### Layer Structure

```
server.py          # FastMCP server - registers MCP tools with @mcp.tool()
    │
    ▼
tools.py           # Tool catalog - wrapper functions that return {status, data/error}
    │
    ▼
services/          # Business logic - SAP operations, OCR, LLM parsing
    └── sap_operations.py   # Core SAP API calls + invoice processing logic
    │
    ▼
utilities/         # Shared utilities
    ├── general.py         # OpenAI client, Cloud Vision OCR
    ├── prompts.py         # LLM prompts for invoice parsing and validation
    ├── image_storage.py   # GCS operations, PDF download
    └── sap_client.py      # SAP authentication helpers
```

### MCP Tools Pipeline

The server exposes 6 tools that form the invoice processing pipeline:

1. `extraer_texto(ruta_gcs)` - Extract text from PDF via Cloud Vision OCR
2. `parsear_factura(texto_factura)` - Structure invoice data using OpenAI (gpt-4o-mini)
3. `validar_proveedor(nombre, nit)` - Find supplier in SAP (tax number match > name similarity > AI fallback)
4. `buscar_ordenes_compra(supplier_code, ...)` - Get purchase orders for supplier
5. `construir_json(factura_datos, proveedor_info, oc_items)` - Build SAP-formatted JSON
6. `enviar_a_sap(factura_json)` - Submit invoice to SAP with CSRF token

### Key Patterns

**Tool Response Format**: All tools return `{status: "success"|"error"|"not_found", data: ..., error: ...}`

**Supplier Search Strategy** (in `buscar_proveedor_en_sap`):
1. Exact tax number match
2. Name similarity >= 60%
3. Keyword matching
4. AI validation (OpenAI fallback)

**SAP Authentication**: Uses CSRF token fetched from invoice endpoint before POST operations.

**PDF Sources**: Supports local paths, `gs://` URIs, `https://storage.googleapis.com/` URLs, and relative blob paths (uses `BUCKET_NAME` env var).

## Environment Variables

Required in `.env` (see `.env.example`):
- `datecKeyCredentials` - GCP service account JSON (for Cloud Vision + GCS)
- `API_OPENAI_KEY` - OpenAI API key
- `SAP_USERNAME`, `SAP_PASSWORD` - SAP S4HANA credentials
- `BUCKET_NAME` - GCS bucket for PDFs (default: `rpa_facturacion`)

Optional SAP endpoint overrides: `SAP_SUPPLIER_URL`, `SAP_PURCHASE_ORDER_URL`, `SAP_INVOICE_POST_URL`

## File Organization

- `tool.py` and `services/sap_operations.py` contain duplicated logic - the canonical implementation is in `services/sap_operations.py`
- `scripts/procesar_factura.py` is a standalone script with its own SAP logic (includes material document handling)
- `scripts/flujo_completo.py` uses the modular tools from `tools.py`

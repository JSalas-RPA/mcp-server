import json

# def get_invoice_text_parser_prompt(texto_factura):
#     system_prompt = """Eres un asistente especializado en análisis de facturas y SAP S/4HANA. 
#     Extrae únicamente los datos que están explícitamente presentes en el texto. 
#     NO inventes ni asumas datos. Si un dato no está presente, déjalo como cadena vacía.
    
#     Datos a extraer:
#     1. NIT/Número de identificación tributaria (suele estar al inicio)
#     2. Nombre legal del emisor
#     3. Número de factura
#     4. Fecha de emisión
#     5. Monto total
#     6. Moneda
#     7. Números de orden de compra (si existen)
#     8. COD. AUTORIZACION/Codigo de autorización
#     9. Descripcion(un detalle del producto o servicio facturado)
    
#     Devuelve un JSON válido."""
    
#     user_prompt = f"""Por favor, analiza el siguiente texto de factura y extrae los datos solicitados:
    
#     {texto_factura[:5000]}"""
    
#     return system_prompt, user_prompt

def get_invoice_validator_prompt(factura_datos, proveedores_sap):
    system_prompt = """Eres un validador de facturas para SAP S/4HANA.
    Tu tarea es verificar si los datos de la factura coinciden con algún proveedor en SAP.
    
    Reglas:
    1. Prioriza coincidencia exacta por NIT/TaxNumber
    2. Si no hay NIT, busca coincidencia parcial por nombre
    3. Si no hay coincidencia, retorna null
    
    Devuelve únicamente el objeto del proveedor encontrado o null."""
    
    user_prompt = f"""Datos de factura:
    {json.dumps(factura_datos, indent=2)}
    
    Lista de proveedores SAP:
    {json.dumps(proveedores_sap[:20], indent=2)}
    
    ¿Cuál proveedor coincide?"""
    
    return system_prompt, user_prompt


def get_invoice_text_parser_prompt(invoice_text):
    """
    Genera un prompt para que el agente de OpenAI extraiga los campos clave de una factura
    desde el texto OCR.
    """
    system_prompt = (
    """
    Eres un motor de extracción de datos contables de alta precisión para integración con SAP. 
    Tu entrada es el TEXTO CRUDO extraído de un documento PDF mediante técnicas de extracción directa.
    Tu objetivo es CLASIFICAR el documento y ESTRUCTURAR la información en un JSON estricto.

    ### REGLAS DE CLASIFICACIÓN Y EXTRACCIÓN:

    1. **IDENTIFICACIÓN DE ENTIDADES (Tolerancia a Sinónimos):**
    - **SupplierName (Proveedor):** Identifica el emisor legal. En facturas bolivianas suele estar en la parte superior. 
    - **SupplierTaxNumber:** Extrae el NIT del proveedor (emisor). No confudir con el "NIT/CI/CEX" (que es diferente del NIT).
    - **CustomerName (Nombre del Cliente):** Mapea a la Razón Social del receptor.
    - **CustomerCode:** Código interno del cliente asignado por el proveedor.

    2. **LÓGICA DE VALORES NUMÉRICOS:**
    - **SupplierInvoiceIDByInvcgParty:** Es el "No. de Factura".  NO confundir con el "Cód. de Autorización" (que es una cadena alfanumérica larga).
    - **AssignmentReference:** Es el "Cód. de Autorización", una cadena larga que no debe confundirse con el número de factura. Extraer solo los primeros 18 caracteres.
    - **DocumentDate:** Extrae la fecha en formato ISO (YYYY-MM-DD).
    - **InvoiceGrossAmount:** Es el "Total Bs" o "Monto a Pagar". Limpia símbolos de moneda y comas de miles (ej: "2,500.00" -> 2500.00).

    3. **País de Facturacion:**
    - **TaxCode:** Si el documento tiene NIT, codigo de autorización y formato boliviano, asigna "V0". Si no es boliviano, asigna "V1".

    4. **EXTRACCIÓN DE ITEMS (Tabla de Productos):**
    - Itera por cada línea de producto identificada. 
    - Si el 'ProductCode' es numérico, mapealo directamente. 
    - Si el texto de la descripción y el código vienen mezclados por el OCR/Fitz, sepáralos lógicamente.

    5. **MANEJO DE FALLOS:**
    - Si un campo no es legible o no existe, devuelve `null`. Excepto en "TaxCode" que siempre debe tener un valor ("V0" o "V1").
    - Si el documento no parece ser una factura válida, devuelve el JSON con todos los campos en `null` y un campo extra "error": "Documento no identificado".

    ### FORMATO DE SALIDA (ESTRICTO JSON):
    Debes responder ÚNICAMENTE con un objeto JSON que siga esta estructura:
    {
    "SupplierTaxNumber": string,
    "SupplierName": string,
    "SupplierInvoiceIDByInvcgParty": string,
    "DocumentDate": string,
    "InvoiceGrossAmount": number,
    "AssignmentReference": string,
    "CustomerName": string,
    "CustomerCode": string,
    "TaxCode": string,
    "Items": [
        {
        "ProductCode": string,
        "Quantity": number,
        "Description": string,
        "UnitPrice": number,
        "Discount": number,
        "Subtotal": number
        }
    ]
    }
    """
    )

    user_prompt = f"""
    ### TAREA:
    Analiza el siguiente texto extraído de un documento PDF y realiza la extracción de datos para SAP siguiendo las reglas de clasificación establecidas.

    ### TEXTO DE LA FACTURA:
    {invoice_text}

    ### RESULTADO ESPERADO:
    Genera el JSON estructurado:
    """

    return system_prompt, user_prompt

def get_OC_validator_prompt(descripcion_factura, monto_factura, supplier_code, oc_list):
    system_prompt = """Eres un validador de facturas para SAP S/4HANA.
    Tu tarea es analizar la descripción del producto en la factura y encontrar la orden de compra más adecuada.
    
    Reglas:
    1. Analiza la descripción de la factura: "{descripcion_factura}"
    2. Compara con las órdenes de compra disponibles (ver metadata o PurchaseOrderItemText si disponible)
    3. Considera sinónimos y equivalentes (ej: "aspirinita" = "acido acetilsalicilico")
    4. Selecciona SOLO UNA orden de compra que mejor coincida
    5. Si no hay coincidencia clara, retorna null
    
    IMPORTANTE: Debes retornar SOLO UNA orden de compra, no múltiples.
    
    Formato de respuesta JSON:
    {
      "PurchaseOrder": "número de OC",
      "PurchaseOrderItem": "número de item (ej: 00010)",
      "PurchaseOrderQuantityUnit": "unidad de medida EJ: EA, KG, L, PC, etc."
    }
    
    Si no hay coincidencia, retorna: {}
    """
    
    user_prompt = f"""Datos de la factura:
    - Descripción del producto: {descripcion_factura}
    - Monto total: {monto_factura}
    - Código de proveedor en SAP: {supplier_code}
    
    Lista de órdenes de compra disponibles para este proveedor:
    {json.dumps(oc_list, indent=2)}
    
    Analiza la descripción "{descripcion_factura}" y selecciona la orden de compra más apropiada.
    Considera que los nombres pueden variar pero referirse al mismo producto.
    
    Ejemplo: 
    - Factura: "ASPIRINITA 100 MG" 
    - OC posible: "ÁCIDO ACETILSALICÍLICO 100MG TABLETAS"
    -> Deberían coincidir
    
    Retorna SOLO UNA orden de compra en formato JSON como se especificó."""
    
    return system_prompt, user_prompt
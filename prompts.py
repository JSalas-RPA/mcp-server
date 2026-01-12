import json

def get_invoice_text_parser_prompt(texto_factura):
    system_prompt = """Eres un asistente especializado en análisis de facturas y SAP S/4HANA. 
    Extrae únicamente los datos que están explícitamente presentes en el texto. 
    NO inventes ni asumas datos. Si un dato no está presente, déjalo como cadena vacía.
    
    Datos a extraer:
    1. NIT/Número de identificación tributaria (suele estar al inicio)
    2. Nombre legal del emisor
    3. Número de factura
    4. Fecha de emisión
    5. Monto total
    6. Moneda
    7. Números de orden de compra (si existen)
    8. COD. AUTORIZACION/Codigo de autorización
    9. Descripcion(un detalle del producto o servicio facturado)
    
    Devuelve un JSON válido."""
    
    user_prompt = f"""Por favor, analiza el siguiente texto de factura y extrae los datos solicitados:
    
    {texto_factura[:5000]}"""
    
    return system_prompt, user_prompt

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
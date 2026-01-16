import json

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

def get_material_entry_validator_prompt(factura_info, oc_info, material_items):
    """
    Prompt para que el LLM seleccione la entrada de material correcta.
    """
    # Convertir los ítems de material a formato legible
    material_items_str = []
    for i, item in enumerate(material_items, 1):
        material_items_str.append(f"""
        ÍTEM {i}:
          • Documento: {item.get('MaterialDocument', 'N/A')}
          • Año: {item.get('MaterialDocumentYear', 'N/A')}
          • Ítem: {item.get('MaterialDocumentItem', 'N/A')}
          • Material: {item.get('Material', 'N/A')}
          • Cantidad: {item.get('QuantityInEntryUnit', 'N/A')} {item.get('EntryUnit', 'N/A')}
          • Planta: {item.get('Plant', 'N/A')}
          • Almacén: {item.get('StorageLocation', 'N/A')}
          • OC: {item.get('PurchaseOrder', 'N/A')} - Ítem OC: {item.get('PurchaseOrderItem', 'N/A')}
          • Fecha: {item.get('DocumentDate', 'N/A')}
        """)
    
    material_items_formatted = "\n".join(material_items_str)
    
    system_prompt = """Eres un experto en SAP MM que debe seleccionar la entrada de material correcta 
    (documento de MIGO) para asociar con una factura de proveedor.

    Tu tarea es analizar los datos de la factura y las entradas de material disponibles,
    y seleccionar la entrada de material MÁS APROPIADA.

    CRITERIOS DE SELECCIÓN (por orden de prioridad):
    1. La entrada debe ser para la misma Orden de Compra (OC) e ítem de OC
    2. La cantidad debe ser la más cercana al monto de la factura
    3. El material debe coincidir o ser similar al descrito en la factura
    4. La fecha debe ser anterior a la fecha de la factura
    5. Si hay varias, selecciona la más reciente

    INFORMACIÓN CLAVE:
    - La factura es por: {monto_factura} BOB
    - El producto en la factura es: {descripcion_producto}

    RESPONDE ÚNICAMENTE con un objeto JSON que contenga:
    {{
        "ReferenceDocument": "Número de documento de material",
        "ReferenceDocumentFiscalYear": "Año fiscal del documento",
        "ReferenceDocumentItem": "Número de ítem del documento"
    }}

    Si NO hay ninguna entrada apropiada, responde con un objeto vacío {{}}."""

    user_prompt = f"""DATOS DE LA FACTURA:
    • Número de Factura: {factura_info.get('supplier_invoice_id', 'N/A')}
    • Proveedor SAP: {factura_info.get('supplier_code', 'N/A')}
    • Fecha Documento: {factura_info.get('document_date', 'N/A')}
    • Monto Total: {factura_info.get('invoice_gross_amount', 'N/A')} BOB
    • Código Autorización: {factura_info.get('assignment_reference', 'N/A')}
    
    PRODUCTOS EN LA FACTURA:
    {json.dumps(factura_info.get('items', []), indent=2, ensure_ascii=False)}
    
    ORDEN DE COMPRA SELECCIONADA:
    • OC: {oc_info.get('PurchaseOrder', 'N/A')}
    • Ítem OC: {oc_info.get('PurchaseOrderItem', 'N/A')}
    • Material OC: {oc_info.get('Material', 'N/A')}
    
    ENTRADAS DE MATERIAL DISPONIBLES (MIGO) - Total: {len(material_items)}:
    {material_items_formatted}
    
    Por favor, selecciona la entrada de material más apropiada basándote en los criterios anteriores.
    Si hay múltiples opciones válidas, selecciona la que tenga la fecha más reciente.
    """
    
    return system_prompt, user_prompt
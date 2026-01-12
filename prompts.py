import json


def get_invoice_validator_prompt(invoice_json, suppliers_json):
    """
    Crea los prompts para OpenAI para extraer datos del proveedor según la factura.
    """
    supplier_name_in_invoice = invoice_json["d"]["SupplierInvoiceIDByInvcgParty"]
    
    system_prompt = """
Eres un agente especializado en procesamiento de facturas. 
Se te proporcionará un nombre de proveedor extraído de una factura y un JSON con los proveedores disponibles.
Tu tarea es buscar dentro del JSON del proveedor cuyo nombre coincida (o sea muy similar) con el de la factura y devolver los campos clave para crear la orden de compras:
- Supplier
- SupplierFullName
- SupplierName
- SupplierAccountGroup

Devuelve solo un JSON con esos campos, sin explicaciones adicionales.
"""
    
    user_prompt = f"""
Proveedor en la factura: "{supplier_name_in_invoice}"

JSON de proveedores: {json.dumps(suppliers_json)}

Busca dentro del JSON de proveedores el proveedor que coincida con el nombre de la factura y devuelve los campos clave en formato JSON.
"""
    
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
    - **NIT:** Extrae el NIT del proveedor (emisor).
    - **SupplierTaxNumber (NIT/CI/CEX):** Diferente del NIT.
    - **CustomerName (Nombre del Cliente):** Mapea a la Razón Social del receptor.
    - **CustomerCode:** Código interno del cliente asignado por el proveedor.

    2. **LÓGICA DE VALORES NUMÉRICOS:**
    - **SupplierInvoiceIDByInvcgParty:** Es el "No. de Factura".  NO confundir con el "Cód. de Autorización" (que es una cadena alfanumérica larga).
    - **AuthCode:** Es el "Cód. de Autorización", una cadena larga que no debe confundirse con el número de factura. Extraer solo los primeros 14 caracteres.
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
    "SupplierInvoiceIDByInvcgParty": string,
    "SupplierName": string,
    "NIT": string,
    "AuthCode": string,
    "SupplierTaxNumber": string,
    "DocumentDate": string,
    "InvoiceGrossAmount": number,
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


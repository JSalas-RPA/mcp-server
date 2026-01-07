import fitz  # PyMuPDF
import openai
import json

def extract_text_from_first_page(file_path: str) -> str:
    """Extrae texto de la primera página del PDF."""
    try:
        doc = fitz.open(file_path)
        if len(doc) == 0:
            return ""
        
        # Extraemos solo la primera página
        page = doc[0]
        text_content = page.get_text().strip()
        
        # Si el texto es casi nulo, asumimos que es imagen (necesitará OCR)
        if len(text_content) < 50:
            return "ERROR:_PDF_SIN_TEXTO_O_ESCANEADO"

        print("Texto extraído de la primera página:", text_content)
        return text_content
    except Exception as e:
        return f"ERROR_PROCESAMIENTO: {str(e)}"

def process_invoice_with_llm(invoice_text: str, api_key: str):
    client = openai.OpenAI(api_key=api_key)
    
    # SYSTEM PROMPT: Aquí definimos el comportamiento y el esquema
    system_instruction = ("""
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
    """)
    
    # USER PROMPT: Solo el recurso y la orden directa
    user_content = f"""
    ### TAREA:
    Analiza el siguiente texto extraído de un documento PDF y realiza la extracción de datos para SAP siguiendo las reglas de clasificación establecidas.

    ### TEXTO DE LA FACTURA:
    {invoice_text}

    ### RESULTADO ESPERADO:
    Genera el JSON estructurado:
    """
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_content}
        ],
        response_format={ "type": "json_object" }
    )
    
    return json.loads(response.choices[0].message.content)

# --- EJECUCIÓN DE PRUEBA ---
if __name__ == "__main__":
    # 1. Configura tu API Key
    MY_API_KEY = "OPENAI_KEY_REMOVED"
    # 2. Ruta de tu archivo
    ARCHIVO = "/home/olguin/Downloads/facturas/factura 31220254.pdf"
    
    print("--- Extrayendo texto ---")
    texto = extract_text_from_first_page(ARCHIVO)
    
    if "ERROR" in texto:
        print(texto)
    else:
        print("--- Enviando a LLM ---")
        resultado = process_invoice_with_llm(texto, MY_API_KEY)
        print(json.dumps(resultado, indent=4, ensure_ascii=False))
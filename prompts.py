


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
        "Eres un asistente experto en facturación. Recibirás el texto completo de una factura y "
        "debes extraer los siguientes campos para generar un JSON válido para SAP:\n"
        "- SupplierInvoiceIDByInvcgParty (Número de factura)\n"
        "- SupplierName (Nombre del proveedor)\n"
        "- SupplierTaxNumber (NIT del proveedor)\n"
        "- DocumentDate\n"
        "- InvoiceGrossAmount\n"
        "- CustomerName\n"
        "- CustomerCode\n"
        "- Items: Lista de productos con ProductCode, Quantity, Description, UnitPrice, Discount, Subtotal\n"
        "Devuelve solo el JSON, sin texto adicional."
    )

    user_prompt = f"Texto de la factura:\n{invoice_text}\nExtrae los datos solicitados en formato JSON."

    return system_prompt, user_prompt


### Extracción de datos de las facturas
Datos requeridos:
- Número de factura: "SupplierInvoiceIDByInvcgParty"
- Nombre del Proveedor: "SupplierName"
- NIT del proovedor: "NIT"
- Codigo de autorización: "AuthCode"
- NIT/CI/CEX: "SupplierTaxNumber"
- Fecha: "DocumentDate"
- Monto Total: "InvoiceGrossAmount"
- Nombre de cliente: "CustomerName"
- Código de cliente: "CustomerCode"
- País: "TaxCode"
- Items: "Items"

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

    ### Validar factura 
    Extraer campos
        empresa_emisora = resultado_factura.get("empresa_emisora", "No detectada")
        nit_factura = resultado_factura.get("nit_factura", "No detectado")
        numero_factura = resultado_factura.get("numero_factura", "No detectado")
        codigo_autorizacion = resultado_factura.get("codigo_autorizacion", "No detectado")
        razon_social_cliente = resultado_factura.get("razon_social_cliente", "No detectada")
        nit_ci_ce_cliente = resultado_factura.get("nit_ci_ce_cliente", "No detectado")
        codigo_cliente = resultado_factura.get("codigo_cliente", "No detectado")
        fecha_emision = resultado_factura.get("fecha_emision", "No detectada")
        direccion = resultado_factura.get("direccion", "No detectada")
        ciudad = resultado_factura.get("ciudad", "No detectada")
        subtotal = resultado_factura.get("subtotal", "No detectado")
        monto_total = resultado_factura.get("monto_total", "No detectado")
        productos = resultado_factura.get("productos", [])
        factura_valida = resultado_factura.get("factura_valida", False)
        vigente = resultado_factura.get("vigente", False)
def get_invoice_validator_prompt(invoice_text):
    """
    Prompt mejorado para facturas bolivianas:
    - Reconoce NIT/CI/CEX del cliente
    - Reconoce nombre del cliente o empresa emisora de la factura
    - Reconoce número de factura
    - Reconoce código de autorización
    - Reconoce subtotal y total
    - Extrae productos y precios en un array
    """

    system_prompt = """
Asume el rol de un verificador experto de facturas bolivianas. 
Tu tarea es analizar el texto OCR y determinar si corresponde a una **factura boliviana válida**.


---

### Heurísticas clave:

**1. empresa_emisora**  
- Aparece en las primeras líneas o junto a “EMISOR”, “FACTURANTE”, “RAZÓN SOCIAL DEL EMISOR”.  
- Ignora textos genéricos (ej. “emizor”, “sistema de facturación”).  
- Concatena líneas contiguas si el nombre está partido.

**2. nit_factura**  
- Cerca del nombre de la empresa emisora o etiquetado como “NIT”.  
- Devuelve solo números (entero).

**3. numero_factura**  
- Etiquetas: “FACTURA N°”, “FACTURA Nº”, “Nº FACTURA”.  
- Extrae número entero.

**4. codigo_autorizacion**  
- Etiquetas: “COD. AUTORIZACIÓN”, “CÓDIGO AUTORIZACIÓN”, “AUTORIZACIÓN”.  
- Puede estar roto por OCR; concatena líneas contiguas si es necesario.  
- Devuelve como string alfanumérico.

**5. razon_social_cliente**  
- Etiquetas: “Nombre/Razón Social”, “Señor(es):”, “CLIENTE”.  
- Combina líneas hasta encontrar otro campo.

**6. nit_ci_ce_cliente**  
- Etiquetas: “NIT/CI/CEX”, “NIT/CI”, “CI/NIT”, “Carnet de Identidad”.  
- Prioriza valor cercano a razón social cliente.  
- Puede ser número o string si es CEX.

**7. codigo_cliente**  
- Etiquetas: “Código Cliente”, “Cod. Cliente”.  
- Extrae números o texto corto.

**8. fecha_emision**  
- Formatos: DD/MM/YYYY, D/M/YYYY, YYYY-MM-DD (con o sin hora).  
- Normaliza a “YYYY-MM-DD”.

**9. direccion**  
- Busca “CALLE”, “AV.”, “EDIFICIO”, “ENTRE AV.”, “BARRIO”.  
- Combina hasta encontrar NIT, Teléfono, Ciudad o Fecha.

**10. ciudad**  
- Palabras clave: “La Paz”, “Santa Cruz”, “Cochabamba”, etc.  
- Elige la más cercana a la dirección o fecha.

**11. subtotal y monto_total**  
- Etiquetas: “SUBTOTAL BS”, “SUBTOTAL”, “TOTAL BS”, “TOTAL A PAGAR BS”, “Importe Base Crédito Fiscal”.  
- Normaliza valores a números decimales.


Salida obligatoria  a la cual siempre se tiene que adptar ya que sera para cargada SAP s4 hana(JSON EXACTO):
    {
    "d": {
        "CompanyCode": "1000",
        "DocumentDate": "2025-10-05T00:00:00",  
        "PostingDate": "2025-10-05T00:00:00", 
        "SupplierInvoiceIDByInvcgParty": "HIPERMAXI S.A.",
        "InvoicingParty": "10000000",
        "DocumentCurrency": "BOB",
        "InvoiceGrossAmount": "2500.00",
        "DueCalculationBaseDate": "2025-10-05T00:00:00", 
        "TaxIsCalculatedAutomatically": true,
        "TaxDeterminationDate": "2025-10-05T00:00:00",  
        "SupplierInvoiceStatus": "A",
        "to_SuplrInvcItemPurOrdRef": {
        "results": [
            {
            "SupplierInvoiceItem": "00001",
            "PurchaseOrder": "4500000004",
            "PurchaseOrderItem": "00020",
            "DocumentCurrency": "BOB",
            "QuantityInPurchaseOrderUnit": "500.000",
            "PurchaseOrderQuantityUnit": "EA",
            "SupplierInvoiceItemAmount": "2500.00",
            "TaxCode": "V0"
            }
        ]
        }
    }
    }


Si no es válida:

{
    "factura_valida": false,
    "vigente": false,
    "empresa_emisora": null,
    "nit_factura": null,
    "numero_factura": null,
    "codigo_autorizacion": null,
    "razon_social_cliente": null,
    "nit_ci_ce_cliente": null,
    "codigo_cliente": null,
    "fecha_emision": null,
    "direccion": null,
    "ciudad": null,
    "subtotal": null,
    "monto_total": null,
    "productos": []
}


Responde solo con el JSON válido, sin explicaciones.
"""

    user_prompt = f"""
Texto del documento (OCR):
\"\"\"{invoice_text}\"\"\"

Instrucciones:
- Aplica todas las heurísticas del system prompt.
- Reconstruye códigos y NITs aunque estén rotos en varias líneas.
- Normaliza números (decimal con punto).
- Extrae productos y precios en un array bajo la clave "productos".
- Devuelve solo un JSON exacto con las claves indicadas.
- Solo no es valida si no tiene empresa emisora, NIT, numero de factura o total.
"""


    return system_prompt, user_prompt





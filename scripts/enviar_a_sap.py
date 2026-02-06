from tools_sap_services.sap_api import enviar_factura_a_sap

factura_json = {
  "CompanyCode": "1000",
  "DocumentDate": "2026-02-04T00:00:00",
  "PostingDate": "2026-02-04T00:00:00",
  "SupplierInvoiceIDByInvcgParty": "0402202603",
  "InvoicingParty": "1000191",
  "AssignmentReference": "0402202603DA31",
  "DocumentCurrency": "BOB",
  "InvoiceGrossAmount": "562.51",
  "DueCalculationBaseDate": "2026-02-04T00:00:00",
  "TaxIsCalculatedAutomatically": True,
  "TaxDeterminationDate": "2026-02-04T00:00:00",
  "SupplierInvoiceStatus": "5",
  "to_SuplrInvcItemPurOrdRef": {
    "results": [
      {
        "SupplierInvoiceItem": "00001",
        "PurchaseOrder": "4500000117",
        "PurchaseOrderItem": "10",
        "DocumentCurrency": "BOB",
        "QuantityInPurchaseOrderUnit": "150.0",
        "PurchaseOrderQuantityUnit": "EA",
        "SupplierInvoiceItemAmount": "489.37500000000006",
        "TaxCode": "C1",
        "ReferenceDocument": "5000000272",
        "ReferenceDocumentFiscalYear": "2026",
        "ReferenceDocumentItem": "1"
      }
    ]
  }
}

factura_json_2 = {
          
  "CompanyCode": "1000",
  "DocumentDate": "2026-02-04T00:00:00",
  "PostingDate": "2026-02-04T00:00:00",
  "SupplierInvoiceIDByInvcgParty": "0402202601",
  "InvoicingParty": "1000191",
  "AssignmentReference": "0402202601DA31",
  "DocumentCurrency": "BOB",
  "InvoiceGrossAmount": "1750.0",
  "DueCalculationBaseDate": "2026-02-04T00:00:00",
  "TaxIsCalculatedAutomatically": true,
  "TaxDeterminationDate": "2026-02-04T00:00:00",
  "SupplierInvoiceStatus": "5",
  "to_SuplrInvcItemPurOrdRef": {
    "results": [
      {
        "SupplierInvoiceItem": "00001",
        "PurchaseOrder": "4500000117",
        "PurchaseOrderItem": "10",
        "DocumentCurrency": "BOB",
        "QuantityInPurchaseOrderUnit": "375.0",
        "PurchaseOrderQuantityUnit": "EA",
        "SupplierInvoiceItemAmount": "1223.4375",
        "TaxCode": "C1",
        "ReferenceDocument": "5000000270",
        "ReferenceDocumentFiscalYear": "2026",
        "ReferenceDocumentItem": "1"
      },
      {
        "SupplierInvoiceItem": "00002",
        "PurchaseOrder": "4500000117",
        "PurchaseOrderItem": "20",
        "DocumentCurrency": "BOB",
        "QuantityInPurchaseOrderUnit": "125.0",
        "PurchaseOrderQuantityUnit": "EA",
        "SupplierInvoiceItemAmount": "299.0625",
        "TaxCode": "C1",
        "ReferenceDocument": "5000000270",
        "ReferenceDocumentFiscalYear": "2026",
        "ReferenceDocumentItem": "2"
      }
    ]
  }
}

def _ejecutar_etapa_envio(factura_json: dict) -> dict:
        """Ejecuta la etapa de envío a SAP."""

        print(f"\n{'='*70}")
        print(f"Enviando json de factura a SAP S4HANA")
        print(f"{'='*70}")

        try:
            print("  Enviando factura a SAP...")
            resultado = enviar_factura_a_sap(factura_json)
            respuesta = resultado.get("d", {})

            if respuesta.get("SupplierInvoiceStatus") != "5":
                raise (f"Error enviando a SAP: {respuesta.get('error')}")

            print("  Factura enviada exitosamente!")
            print(f"Número de factura SAP: {respuesta.get('SupplierInvoice')}")

            

            return respuesta

        except Exception as e:
            print(f"  Error enviando factura a SAP: {str(e)}")
            return {"status": "error", "error": str(e)}
            
        
if __name__ == "__main__":
    _ejecutar_etapa_envio(factura_json)
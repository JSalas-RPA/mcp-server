from tools_sap_services.sap_api import enviar_factura_a_sap

factura_json = {
          "CompanyCode": "1000",
          "DocumentDate": "2026-01-28T00:00:00",
          "PostingDate": "2026-01-29T00:00:00",
          "SupplierInvoiceIDByInvcgParty": "2801202604",
          "InvoicingParty": "1000191",
          "AssignmentReference": "2801202606DA31",
          "DocumentCurrency": "BOB",
          "InvoiceGrossAmount": "1250",
          "DueCalculationBaseDate": "2026-01-28T00:00:00",
          "TaxIsCalculatedAutomatically":True,
          "TaxDeterminationDate": "2026-01-28T00:00:00",
          "SupplierInvoiceStatus": "5",
          "to_SuplrInvcItemPurOrdRef": {
            "results": [
              {
                "SupplierInvoiceItem": "00001",
                "PurchaseOrder": "4500000115",
                "PurchaseOrderItem": "10",
                "DocumentCurrency": "BOB",
                "QuantityInPurchaseOrderUnit": "125.0",
                "PurchaseOrderQuantityUnit": "EA",
                "SupplierInvoiceItemAmount": "1087.5",
                "TaxCode": "C1",
                "ReferenceDocument": "5000000265",
                "ReferenceDocumentFiscalYear": "2026",
                "ReferenceDocumentItem": "1"
              }
            ]
          }
        }
factura_json_2 = {
          "CompanyCode": "1000",
          "DocumentDate": "2026-01-28T00:00:00",
          "PostingDate": "2026-01-29T00:00:00",
          "SupplierInvoiceIDByInvcgParty": "2801202605",
          "InvoicingParty": "1000191",
          "AssignmentReference": "2801202605DA31",
          "DocumentCurrency": "BOB",
          "InvoiceGrossAmount": "1750",
          "DueCalculationBaseDate": "2026-01-28T00:00:00",
          "TaxIsCalculatedAutomatically": True,
          "TaxDeterminationDate": "2026-01-28T00:00:00",
          "SupplierInvoiceStatus": "5",
          "to_SuplrInvcItemPurOrdRef": {
            "results": [
              {
                "SupplierInvoiceItem": "00001",
                "PurchaseOrder": "4500000115",
                "PurchaseOrderItem": "10",
                "DocumentCurrency": "BOB",
                "QuantityInPurchaseOrderUnit": "175.0",
                "PurchaseOrderQuantityUnit": "EA",
                "SupplierInvoiceItemAmount": "1522.5",
                "TaxCode": "C1",
                "ReferenceDocument": "5000000266",
                "ReferenceDocumentFiscalYear": "2026",
                "ReferenceDocumentItem": "1"
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

            if resultado.get("status") != "success":
                raise (f"Error enviando a SAP: {resultado.get('error')}")

            respuesta = resultado["data"]
            print("  Factura enviada exitosamente!")

            

            return respuesta

        except Exception as e:
            print(f"  Error enviando factura a SAP: {str(e)}")
            return {"status": "error", "error": str(e)}
            
        
if __name__ == "__main__":
    _ejecutar_etapa_envio(factura_json_2)
# services/sap_operations.py
# ============================================
# Operaciones de negocio SAP S4HANA
# ============================================
# Este módulo contiene la lógica de negocio principal:
# - Búsqueda de proveedores
# - Construcción de JSON para facturas
#
# Las operaciones de matching (OC, MIGO) están en services/matchers/
# Las llamadas HTTP puras están en services/sap_api.py
# Las funciones de IA están en utilities/llm_client.py
# ============================================

import logging
from datetime import datetime

from utilities.text_utils import (
    calcular_similitud_nombres,
    limpiar_nombre_minimo,
    extraer_solo_numeros,
)
from utilities.date_utils import format_sap_date
from utilities.llm_client import validar_proveedor_con_ai

# Re-exportar funciones para compatibilidad con imports existentes
from services.sap_api import (
    obtener_proveedores_sap,
    enviar_factura_a_sap,
)
from services.matchers import (
    obtener_ordenes_compra_proveedor,
    verificar_entradas_material,
    SCORE_CONFIG,
    MIGO_CONFIG,
)
from utilities.llm_client import (
    extraer_datos_factura_desde_texto,
    comparar_descripciones_con_ia,
)

logger = logging.getLogger(__name__)


# ============================================
# BÚSQUEDA DE PROVEEDORES
# ============================================

def buscar_proveedor_en_sap(factura_datos: dict, proveedores_sap: list) -> dict | None:
    """
    Busca y valida el proveedor en la lista de proveedores de SAP.
    Estrategia de búsqueda múltiple robusta:
    1. Tax Number exacto
    2. Similitud de nombres completos
    3. Coincidencia de palabras clave
    4. AI como fallback
    """
    tax_buscar = str(factura_datos.get("SupplierTaxNumber", "")).strip()
    nombre_buscar_original = factura_datos.get("SupplierName", "").strip()
    nombre_buscar = limpiar_nombre_minimo(nombre_buscar_original)

    print("\n" + "=" * 70)
    print("BUSCANDO PROVEEDOR EN SAP:")
    print("=" * 70)
    print(f"  Nombre original: {nombre_buscar_original}")
    print(f"  Nombre limpio: {nombre_buscar}")
    print(f"  Tax Number: {tax_buscar}")
    print("=" * 70)

    logger.info(f"Buscando proveedor en SAP: '{nombre_buscar_original}' (Tax: {tax_buscar})")

    resultados = []

    # ESTRATEGIA 1: Búsqueda exacta por Tax Number (MÁS CONFIABLE)
    if tax_buscar and tax_buscar != "":
        print(f"  ESTRATEGIA 1: Busqueda exacta por Tax Number")
        for proveedor in proveedores_sap:
            tax_campos = ['TaxNumber1', 'TaxNumber', 'SupplierTaxNumber']
            tax_proveedor = ""

            for campo in tax_campos:
                if campo in proveedor and proveedor[campo]:
                    tax_proveedor = extraer_solo_numeros(str(proveedor[campo]))
                    break

            if tax_proveedor and tax_proveedor == tax_buscar:
                print(f"    [OK] ENCONTRADO: Tax {tax_buscar} coincide exactamente")

                supplier_name = proveedor.get('SupplierName') or proveedor.get('BusinessPartnerName') or "N/A"
                supplier_code = proveedor.get('Supplier') or proveedor.get('BusinessPartner') or "N/A"
                supplier_full = proveedor.get('SupplierFullName') or proveedor.get('BusinessPartnerFullName') or supplier_name

                resultados.append({
                    "Supplier": supplier_code,
                    "SupplierFullName": supplier_full,
                    "SupplierName": supplier_name,
                    "SupplierAccountGroup": proveedor.get('SupplierAccountGroup') or proveedor.get('BusinessPartnerGrouping') or "N/A",
                    "TaxNumber": tax_proveedor,
                    "Similitud": 1.0,
                    "Metodo": "Tax Number Exacto"
                })
                break

    # ESTRATEGIA 2: Búsqueda por similitud de nombres COMPLETOS
    if not resultados:
        print(f"  ESTRATEGIA 2: Busqueda por similitud de nombres completos")
        for proveedor in proveedores_sap:
            supplier_name = proveedor.get('SupplierName') or proveedor.get('BusinessPartnerName') or ""
            supplier_full = proveedor.get('SupplierFullName') or proveedor.get('BusinessPartnerFullName') or supplier_name

            supplier_name_limpio = limpiar_nombre_minimo(supplier_name)
            supplier_full_limpio = limpiar_nombre_minimo(supplier_full)

            similitud_name = calcular_similitud_nombres(nombre_buscar, supplier_name_limpio)
            similitud_full = calcular_similitud_nombres(nombre_buscar, supplier_full_limpio)

            similitud = max(similitud_name, similitud_full)

            if similitud >= 0.6:
                resultados.append({
                    "Supplier": proveedor.get('Supplier') or proveedor.get('BusinessPartner') or "N/A",
                    "SupplierFullName": supplier_full,
                    "SupplierName": supplier_name,
                    "SupplierAccountGroup": proveedor.get('SupplierAccountGroup') or proveedor.get('BusinessPartnerGrouping') or "N/A",
                    "TaxNumber": extraer_solo_numeros(str(proveedor.get('TaxNumber1') or proveedor.get('TaxNumber') or "")),
                    "Similitud": similitud,
                    "Metodo": f"Similitud de Nombres ({similitud * 100:.1f}%)"
                })

    # ESTRATEGIA 3: Búsqueda por palabras clave
    if not resultados and nombre_buscar:
        print(f"  ESTRATEGIA 3: Busqueda por palabras clave")
        palabras_clave = nombre_buscar.split()
        for proveedor in proveedores_sap:
            supplier_name = proveedor.get('SupplierName') or proveedor.get('BusinessPartnerName') or ""
            supplier_full = proveedor.get('SupplierFullName') or proveedor.get('BusinessPartnerFullName') or supplier_name

            nombre_combinado = f"{supplier_name} {supplier_full}".upper()
            coincidencias = 0

            for palabra in palabras_clave:
                if palabra and palabra in nombre_combinado:
                    coincidencias += 1

            if coincidencias >= max(1, len(palabras_clave) * 0.5):
                similitud = coincidencias / len(palabras_clave) if palabras_clave else 0
                resultados.append({
                    "Supplier": proveedor.get('Supplier') or proveedor.get('BusinessPartner') or "N/A",
                    "SupplierFullName": supplier_full,
                    "SupplierName": supplier_name,
                    "SupplierAccountGroup": proveedor.get('SupplierAccountGroup') or proveedor.get('BusinessPartnerGrouping') or "N/A",
                    "TaxNumber": extraer_solo_numeros(str(proveedor.get('TaxNumber1') or proveedor.get('TaxNumber') or "")),
                    "Similitud": similitud,
                    "Metodo": f"Coincidencia de Palabras ({coincidencias}/{len(palabras_clave)})"
                })

    # Seleccionar el mejor resultado
    if resultados:
        resultados.sort(key=lambda x: x["Similitud"], reverse=True)
        mejor_resultado = resultados[0]

        print(f"  [OK] PROVEEDOR ENCONTRADO:")
        print(f"     Metodo: {mejor_resultado['Metodo']}")
        print(f"     Nombre: {mejor_resultado['SupplierName']}")
        print(f"     Codigo SAP: {mejor_resultado['Supplier']}")
        print(f"     Tax: {mejor_resultado['TaxNumber']}")
        print(f"     Similitud: {mejor_resultado['Similitud'] * 100:.1f}%")

        if tax_buscar and mejor_resultado['TaxNumber'] and tax_buscar != mejor_resultado['TaxNumber']:
            print(f"  [!] ADVERTENCIA: Tax number no coincide (Factura: {tax_buscar}, SAP: {mejor_resultado['TaxNumber']})")
            logger.warning(f"Tax number no coincide: factura={tax_buscar}, SAP={mejor_resultado['TaxNumber']}")

        logger.info(f"Proveedor encontrado por {mejor_resultado['Metodo']}: {mejor_resultado['SupplierName']}")

        return {
            "Supplier": mejor_resultado["Supplier"],
            "SupplierFullName": mejor_resultado["SupplierFullName"],
            "SupplierName": mejor_resultado["SupplierName"],
            "SupplierAccountGroup": mejor_resultado["SupplierAccountGroup"],
            "TaxNumber": mejor_resultado["TaxNumber"],
            "MetodoBusqueda": mejor_resultado["Metodo"],
            "Similitud": mejor_resultado["Similitud"]
        }

    # ESTRATEGIA 4: Usar AI si todo falla
    print("  ESTRATEGIA 4: Usando AI para validacion (metodos anteriores fallaron)")
    logger.warning("Proveedor no encontrado por busqueda directa. Usando AI para validacion...")
    proveedor_ai = validar_proveedor_con_ai(factura_datos, proveedores_sap)
    if proveedor_ai:
        proveedor_ai["MetodoBusqueda"] = "AI (OpenAI)"
        proveedor_ai["Similitud"] = 0.0
        return proveedor_ai

    return None


# ============================================
# CONSTRUCCIÓN DE JSON PARA SAP
# ============================================

def construir_json_factura_sap(
    factura_datos: dict,
    proveedor_info: dict,
    oc_items: list,
    needs_migo: bool = False,
    reference_document: dict = None
) -> dict | None:
    """
    Construye el JSON final en el formato exacto que SAP espera.

    Args:
        factura_datos: Datos de la factura del parseo OCR
        proveedor_info: Información del proveedor de SAP
        oc_items: Lista de items de OC seleccionados
        needs_migo: Si True, se incluyen campos ReferenceDocument (requiere entrada de material)
        reference_document: Datos del documento de referencia (MIGO) si needs_migo=True
            {
                "ReferenceDocument": "5000000244",
                "ReferenceDocumentFiscalYear": "2025",
                "ReferenceDocumentItem": "1"
            }

    Returns:
        dict con el JSON para SAP o None si hay error
    """
    print("\n" + "=" * 70)
    print("CONSTRUYENDO JSON PARA SAP")
    print("=" * 70)

    if not proveedor_info:
        raise ValueError("Informacion del proveedor no disponible")

    fecha_documento = format_sap_date(factura_datos.get("DocumentDate"))
    fecha_actual = datetime.now().strftime("%Y-%m-%d")
    fecha_actual = format_sap_date(fecha_actual)
    invoice_id = factura_datos.get("SupplierInvoiceIDByInvcgParty", "")

    if not invoice_id or invoice_id == "0":
        print("  [!] No se encontro ID de factura, generando automatico...")
        logger.warning("No se encontro ID de factura, generando automatico")
        invoice_id = f"INV{datetime.now().strftime('%Y%m%d%H%M%S')}"

    invoice_amount = factura_datos.get("InvoiceGrossAmount", 0.0)
    invoice_amount_str = f"{invoice_amount:.0f}"

    cod_autorizacion = factura_datos.get("AssignmentReference", "")
    print(f"  Codigo de Autorizacion inicial: {cod_autorizacion}")
    cod_autorizacion = cod_autorizacion[:14]
    if not cod_autorizacion:
        cod_autorizacion = factura_datos.get("AuthorizationCode", "")
    if not cod_autorizacion:
        cod_autorizacion = ""

    print(f"  DATOS PARA CONSTRUIR JSON:")
    print(f"     N Factura: {invoice_id}")
    print(f"     Proveedor SAP: {proveedor_info.get('Supplier')}")
    print(f"     Codigo Autorizacion: {cod_autorizacion[:50]}...")
    print(f"     Monto: {invoice_amount_str} BOB")
    print(f"     Fecha: {fecha_documento}")
    print(f"     OCs encontradas: {len(oc_items)}")
    print(f"     Requiere MIGO: {'Si' if needs_migo else 'No'}")

    factura_json = {
        "CompanyCode": "1000",
        "DocumentDate": fecha_documento,
        "PostingDate": fecha_actual,
        "SupplierInvoiceIDByInvcgParty": invoice_id,
        "InvoicingParty": proveedor_info.get("Supplier", ""),
        "AssignmentReference": cod_autorizacion,
        "DocumentCurrency": "BOB",
        "InvoiceGrossAmount": invoice_amount_str,
        "DueCalculationBaseDate": fecha_documento,
        "TaxIsCalculatedAutomatically": True,
        "TaxDeterminationDate": fecha_documento,
        "SupplierInvoiceStatus": "5",
        "to_SuplrInvcItemPurOrdRef": {
            "results": []
        }
    }

    if not oc_items:
        logger.error("No se encontraron ordenes de compra para esta factura")
        return None

    print(f"  AGREGANDO {len(oc_items)} ITEMS DE OC:")

    for idx, oc in enumerate(oc_items, start=1):
        raw_amount = oc.get("SupplierInvoiceItemAmount", 0.0)
        invoice_item_amount = float(str(raw_amount).replace(",", "").strip())
        invoice_item_amount = invoice_item_amount/(1+(13/87))  # Ajuste por IGV 13% (temporal hasta corregir en SAP)
        invoice_item_amount_str = str(invoice_item_amount)
        print(f"     Calculando monto item {idx}: Original {oc.get('SupplierInvoiceItemAmount', 0.0)} -> Ajustado {invoice_item_amount_str}")
        item = {
            "SupplierInvoiceItem": str(idx).zfill(5),
            "PurchaseOrder": oc.get("PurchaseOrder", ""),
            "PurchaseOrderItem": oc.get("PurchaseOrderItem", ""),
            "DocumentCurrency": "BOB",
            "QuantityInPurchaseOrderUnit": oc.get("QuantityInPurchaseOrderUnit", ""),
            "PurchaseOrderQuantityUnit": oc.get("PurchaseOrderQuantityUnit", ""),
            "SupplierInvoiceItemAmount": invoice_item_amount_str,
            #"TaxCode": oc.get("TaxCode", "V0")
            "TaxCode": "C1"
        }

        # Solo agregar campos ReferenceDocument si needs_migo es True
        if needs_migo:
            if reference_document:
                item["ReferenceDocument"] = reference_document.get("ReferenceDocument", "")
                item["ReferenceDocumentFiscalYear"] = reference_document.get("ReferenceDocumentFiscalYear", "")
                item["ReferenceDocumentItem"] = reference_document.get("ReferenceDocumentItem", "1")
                print(f"     Item {idx}: OC {oc.get('PurchaseOrder')}, Item {oc.get('PurchaseOrderItem')} "
                      f"[MIGO: {reference_document.get('ReferenceDocument')}]")
            else:
                logger.warning(f"needs_migo=True pero no se proporciono reference_document para item {idx}")
                print(f"     [!] Item {idx}: OC {oc.get('PurchaseOrder')} - FALTA MIGO!")
        else:
            print(f"     Item {idx}: OC {oc.get('PurchaseOrder')}, Item {oc.get('PurchaseOrderItem')} [Directo]")

        factura_json["to_SuplrInvcItemPurOrdRef"]["results"].append(item)

    return factura_json


# ============================================
# FUNCIONES DEPRECADAS (para compatibilidad)
# ============================================

def obtener_entradas_material_por_oc(purchase_order, purchase_order_item=None, supplier_code=None):
    """DEPRECADA: Usar verificar_entradas_material() en su lugar."""
    logger.warning("obtener_entradas_material_por_oc esta deprecada, usar verificar_entradas_material")
    from services.sap_api import fetch_entradas_material
    resultado = fetch_entradas_material(purchase_order, purchase_order_item)
    return resultado.get("data", []) if resultado.get("status") == "success" else []


def validar_y_seleccionar_entrada_material(factura_info, oc_info, entradas_material):
    """DEPRECADA: Usar verificar_entradas_material() en su lugar."""
    logger.warning("validar_y_seleccionar_entrada_material esta deprecada")
    if not entradas_material:
        return {}
    primera = entradas_material[0]
    return {
        "ReferenceDocument": primera.get('MaterialDocument', ''),
        "ReferenceDocumentFiscalYear": primera.get('MaterialDocumentYear', ''),
        "ReferenceDocumentItem": primera.get('MaterialDocumentItem', '1')
    }

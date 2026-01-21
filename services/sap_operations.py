# services/sap_operations.py
# ============================================
# Lógica de negocio para operaciones SAP S4HANA
# ============================================

import json
import logging
import requests
from datetime import datetime

from utilities.sap_client import (
    SAP_CONFIG,
    safe_json_response,
    obtener_sesion_con_token,
    get_sap_auth,
    get_sap_headers,
)
from utilities.text_utils import (
    calcular_similitud_nombres,
    limpiar_nombre_minimo,
    extraer_solo_numeros,
    clean_openai_json,
)
from utilities.date_utils import format_sap_date
from utilities.prompts import (
    get_invoice_text_parser_prompt,
    get_invoice_validator_prompt,
    get_OC_validator_prompt,
)
from utilities.general import get_openai_answer

logger = logging.getLogger(__name__)


# ============================================
# EXTRACCIÓN DE DATOS DE FACTURA
# ============================================

def extraer_datos_factura_desde_texto(texto_factura: str) -> dict:
    """
    Extrae datos principales de la factura desde texto OCR usando OpenAI.
    Transforma y valida los campos extraídos.
    """
    try:
        system_prompt, user_prompt = get_invoice_text_parser_prompt(texto_factura)

        logger.info("📝 Llamando a OpenAI para extraer datos de factura...")
        raw_result = get_openai_answer(system_prompt, user_prompt)

        raw_result = clean_openai_json(raw_result)
        datos = json.loads(raw_result)

        print("\n" + "=" * 70)
        print("📋 DATOS EXTRAÍDOS DE LA FACTURA (OpenAI):")
        print("=" * 70)
        print(json.dumps(datos, indent=2, ensure_ascii=False))
        print("=" * 70)

        datos_transformados = datos.copy()

        # Validar campos requeridos
        campos_requeridos = [
            "SupplierName",
            "SupplierInvoiceIDByInvcgParty",
            "InvoiceGrossAmount",
            "DocumentDate",
            "Items"
        ]
        for campo in campos_requeridos:
            if campo not in datos_transformados:
                logger.warning(f"Campo requerido '{campo}' no encontrado en datos extraídos")

        # Limpiar Tax Number
        if "SupplierTaxNumber" in datos_transformados and datos_transformados["SupplierTaxNumber"]:
            datos_transformados["SupplierTaxNumber"] = extraer_solo_numeros(
                str(datos_transformados["SupplierTaxNumber"])
            )

        # Formatear fecha
        if "DocumentDate" in datos_transformados:
            datos_transformados["DocumentDate"] = format_sap_date(datos_transformados["DocumentDate"])

        # Limpiar monto
        if "InvoiceGrossAmount" in datos_transformados:
            try:
                monto_str = str(datos_transformados["InvoiceGrossAmount"])
                monto_str = monto_str.replace(',', '').replace('Bs', '').replace('$', '').replace('BOB', '').strip()
                datos_transformados["InvoiceGrossAmount"] = float(monto_str)
            except (ValueError, TypeError) as e:
                logger.error(f"Formato de monto inválido: {datos_transformados['InvoiceGrossAmount']} - Error: {e}")
                datos_transformados["InvoiceGrossAmount"] = 0.0

        logger.info("✓ Datos de factura extraídos y transformados exitosamente")
        return datos_transformados

    except json.JSONDecodeError as e:
        logger.error(f"Error al parsear respuesta de OpenAI: {e}")
        raise
    except Exception as e:
        logger.error(f"Error en extracción de datos de factura: {e}")
        raise


# ============================================
# PROVEEDORES SAP
# ============================================

def obtener_proveedores_sap() -> list:
    """
    Obtiene todos los proveedores desde SAP API.
    """
    try:
        headers = get_sap_headers()

        logger.info("🔍 Obteniendo lista de proveedores desde SAP...")
        response = requests.get(
            SAP_CONFIG['supplier_url'],
            headers=headers,
            auth=get_sap_auth(),
            timeout=30
        )

        if response.status_code == 200:
            data = safe_json_response(response)
            if data:
                proveedores = data.get("d", {}).get("results", [])
                logger.info(f"✓ {len(proveedores)} proveedores obtenidos de SAP")

                print("\n" + "=" * 70)
                print("📋 PROVEEDORES OBTENIDOS DE SAP (primeros 10):")
                print("=" * 70)
                for i, proveedor in enumerate(proveedores[:10]):
                    supplier_name = proveedor.get('SupplierName') or proveedor.get('BusinessPartnerName') or "N/A"
                    supplier_code = proveedor.get('Supplier') or proveedor.get('BusinessPartner') or "N/A"
                    tax_number = proveedor.get('TaxNumber1') or proveedor.get('TaxNumber') or "N/A"

                    print(f"  {i + 1:2d}. {supplier_name[:40]:40} | Código: {supplier_code:10} | Tax: {tax_number}")
                if len(proveedores) > 10:
                    print(f"  ... y {len(proveedores) - 10} más")
                print("=" * 70)

                return proveedores
        else:
            logger.error(f"Error {response.status_code} al obtener proveedores de SAP")
            print(f"\n❌ Error al obtener proveedores: Status {response.status_code}")
            print(f"   Respuesta: {response.text[:200]}")

    except Exception as e:
        logger.error(f"Excepción en obtener_proveedores_sap: {e}")

    return []


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
    print("🔍 BUSCANDO PROVEEDOR EN SAP:")
    print("=" * 70)
    print(f"  Nombre original: {nombre_buscar_original}")
    print(f"  Nombre limpio: {nombre_buscar}")
    print(f"  Tax Number: {tax_buscar}")
    print("=" * 70)

    logger.info(f"Buscando proveedor en SAP: '{nombre_buscar_original}' (Tax: {tax_buscar})")

    resultados = []

    # ESTRATEGIA 1: Búsqueda exacta por Tax Number (MÁS CONFIABLE)
    if tax_buscar and tax_buscar != "":
        print(f"  🔍 ESTRATEGIA 1: Búsqueda exacta por Tax Number")
        for proveedor in proveedores_sap:
            tax_campos = ['TaxNumber1', 'TaxNumber', 'SupplierTaxNumber']
            tax_proveedor = ""

            for campo in tax_campos:
                if campo in proveedor and proveedor[campo]:
                    tax_proveedor = extraer_solo_numeros(str(proveedor[campo]))
                    break

            if tax_proveedor and tax_proveedor == tax_buscar:
                print(f"    ✅ ENCONTRADO: Tax {tax_buscar} coincide exactamente")

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
        print(f"  🔍 ESTRATEGIA 2: Búsqueda por similitud de nombres completos")
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
        print(f"  🔍 ESTRATEGIA 3: Búsqueda por palabras clave")
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

        print(f"  ✅ PROVEEDOR ENCONTRADO:")
        print(f"     • Método: {mejor_resultado['Metodo']}")
        print(f"     • Nombre: {mejor_resultado['SupplierName']}")
        print(f"     • Código SAP: {mejor_resultado['Supplier']}")
        print(f"     • Tax: {mejor_resultado['TaxNumber']}")
        print(f"     • Similitud: {mejor_resultado['Similitud'] * 100:.1f}%")

        if tax_buscar and mejor_resultado['TaxNumber'] and tax_buscar != mejor_resultado['TaxNumber']:
            print(f"  ⚠️  ADVERTENCIA: Tax number no coincide (Factura: {tax_buscar}, SAP: {mejor_resultado['TaxNumber']})")
            logger.warning(f"Tax number no coincide: factura={tax_buscar}, SAP={mejor_resultado['TaxNumber']}")

        logger.info(f"✓ Proveedor encontrado por {mejor_resultado['Metodo']}: {mejor_resultado['SupplierName']}")

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
    print("  🔍 ESTRATEGIA 4: Usando AI para validación (métodos anteriores fallaron)")
    logger.warning("Proveedor no encontrado por búsqueda directa. Usando AI para validación...")
    proveedor_ai = validar_proveedor_con_ai(factura_datos, proveedores_sap)
    if proveedor_ai:
        proveedor_ai["MetodoBusqueda"] = "AI (OpenAI)"
        proveedor_ai["Similitud"] = 0.0
        return proveedor_ai

    return None


def validar_proveedor_con_ai(factura_datos: dict, proveedores_sap: list) -> dict | None:
    """
    Usa OpenAI para validar y encontrar el proveedor correcto cuando la búsqueda directa falla.
    """
    try:
        factura_datos_wrapped = {"d": factura_datos}
        system_prompt, user_prompt = get_invoice_validator_prompt(factura_datos_wrapped, proveedores_sap)
        print("  🤖 Consultando a OpenAI para validar proveedor...")
        raw_result = get_openai_answer(system_prompt, user_prompt)
        raw_result = clean_openai_json(raw_result)

        proveedor_info = json.loads(raw_result)
        print(f"  ✅ Proveedor validado por AI: {proveedor_info.get('SupplierName')}")
        logger.info(f"✓ Proveedor validado por AI: {proveedor_info.get('SupplierName')}")
        return proveedor_info

    except Exception as e:
        logger.error(f"Error en validación de proveedor con AI: {e}")
        return None

# ============================================
# ÓRDENES DE COMPRA
# ============================================

def obtener_ordenes_compra_proveedor(
    descripcion_factura: str,
    monto_factura: float,
    supplier_code: str,
    tax_code: str
) -> list:
    """
    Obtiene las órdenes de compra activas para un proveedor específico.
    Usa AI para seleccionar la OC más apropiada.
    """
    try:
        headers = get_sap_headers()
        print({descripcion_factura, monto_factura, supplier_code})

        if not supplier_code:
            logger.warning("No se proporcionó código de proveedor para obtener órdenes de compra")
            return []

        url = f"{SAP_CONFIG['purchase_order_url']}?$filter=Supplier eq '{supplier_code}'&$expand=to_PurchaseOrderItem"
        print(f"\n🔍 BUSCANDO ÓRDENES DE COMPRA PARA PROVEEDOR {supplier_code}")
        print("=" * 50)
        print(f"  Método: GET")
        print(f"  URL: {url}")
        print(f"  Usuario: {SAP_CONFIG['username']}")

        response = requests.get(
            url,
            headers=headers,
            auth=get_sap_auth(),
            timeout=30
        )

        print(f"  📊 Status Code: {response.status_code}")

        if response.status_code == 200:
            data = safe_json_response(response)
            if data and "d" in data and "results" in data["d"]:
                oc_list = data["d"]["results"]
                if oc_list:
                    print(f"  ✅ {len(oc_list)} órdenes de compra encontradas:")
                    print("  " + "-" * 40)

                    for i, oc in enumerate(oc_list):
                        oc_num = oc.get('PurchaseOrder', 'N/A')
                        oc_item = oc.get('Language', 'N/A')
                        oc_status = oc.get('PaymentTerms', 'N/A')
                        oc_date = oc.get('CreationDate', 'N/A')

                        print(f"    {i + 1:2d}. OC: {oc_num:15} | Item: {oc_item:8} | Status: {oc_status:10} | Fecha: {oc_date}")

                    print("  " + "-" * 40)

                    # Usar IA para seleccionar la OC más apropiada
                    system_prompt, user_prompt = get_OC_validator_prompt(
                        descripcion_factura,
                        monto_factura,
                        supplier_code,
                        oc_list
                    )
                    raw_result = get_openai_answer(system_prompt, user_prompt)
                    raw_result = clean_openai_json(raw_result)

                    oc_info = json.loads(raw_result)

                    if oc_info and "PurchaseOrder" in oc_info:
                        print(f"  📋 OC SELECCIONADA POR IA:")
                        print(f"     • OC {oc_info.get('PurchaseOrder')} - Item {oc_info.get('PurchaseOrderItem')}")

                        print(oc_info.get('PurchaseOrderQuantityUnit', ''), )

                        return [{
                            "PurchaseOrder": oc_info.get('PurchaseOrder'),
                            "PurchaseOrderItem": oc_info.get('PurchaseOrderItem', ''),
                            "DocumentCurrency": "BOB",
                            "QuantityInPurchaseOrderUnit": "1.000",
                            "PurchaseOrderQuantityUnit": oc_info.get('PurchaseOrderQuantityUnit', ''),
                            "SupplierInvoiceItemAmount": str(monto_factura),
                            "TaxCode": tax_code or oc_info.get('TaxCode', 'V0')
                        }]
                    else:
                        print(f"  ⚠️  IA no pudo identificar una OC específica")
                        logger.warning(f"IA no pudo identificar una OC específica para proveedor {supplier_code}")
                        return []
                else:
                    print(f"  ⚠️  No se encontraron órdenes de compra para el proveedor {supplier_code}")
                    logger.warning(f"ℹ️ No se encontraron órdenes de compra para el proveedor {supplier_code}")
            else:
                print(f"  ⚠️  No se encontraron datos en la respuesta")
                logger.warning("No se encontraron datos de órdenes de compra en la respuesta")

        elif response.status_code == 403:
            print(f"  ❌ ERROR 403: Permisos insuficientes")
            print(f"     Usuario: {SAP_CONFIG['username']}")
            print(f"     Endpoint: {url}")
            print(f"     Contactar al administrador SAP para agregar permisos")
            logger.warning(f"No se pudo acceder a API de órdenes de compra (Status: 403 - Forbidden)")
            return []
        else:
            print(f"  ❌ Error {response.status_code}: {response.text[:200]}")
            logger.warning(f"No se pudo acceder a API de órdenes de compra (Status: {response.status_code})")

    except Exception as e:
        print(f"  ❌ Excepción: {e}")
        logger.error(f"Error al obtener órdenes de compra: {e}")

    return []

# ============================================
# Verificar la entrada del material (MIGO)
# ============================================

def obtener_entradas_material_por_oc(purchase_order, purchase_order_item=None, supplier_code=None):
    """
    Obtiene las entradas de material (MIGO) asociadas a una orden de compra específica.
    """
    try:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        print(f"\n🔍 BUSCANDO ENTRADAS DE MATERIAL PARA OC {purchase_order}")
        print("="*60)
        
        # URL original que funcionaba - SIN $select para evitar problemas
        url = f"{SAP_CONFIG['material_doc_url']}?$filter=PurchaseOrder eq '{purchase_order}'"
        
        print(f"  URL: {url}")
        
        response = requests.get(
            url,
            headers=headers,
            auth=get_sap_auth(),
            timeout=30
        )
        
        print(f"  Status: {response.status_code}")
        
        if response.status_code == 200:
            data = safe_json_response(response)
            if data and "d" in data and "results" in data["d"]:
                entradas = data["d"]["results"]
                print(f"  ✅ {len(entradas)} entradas de material encontradas")
                
                # Mostrar las entradas disponibles
                for i, entrada in enumerate(entradas[:5]):  # Mostrar máximo 5
                    doc_year = entrada.get('MaterialDocumentYear', 'N/A')
                    doc_num = entrada.get('MaterialDocument', 'N/A')
                    doc_item = entrada.get('MaterialDocumentItem', 'N/A')
                    
                    print(f"    {i+1}. Doc: {doc_num}/{doc_year} - Ítem: {doc_item}")
                
                if len(entradas) > 5:
                    print(f"    ... y {len(entradas) - 5} más")
                
                return entradas
            else:
                print(f"  ⚠️  No se encontraron entradas de material")
                return []
        elif response.status_code == 403:
            print(f"  ❌ ERROR 403: Permisos insuficientes para el endpoint de materiales")
            print(f"     Contactar al administrador SAP para agregar permisos a:")
            print(f"     {SAP_CONFIG['material_doc_url']}")
            logger.error(f"Error 403 al acceder a API de materiales: {response.text[:200]}")
            return []
        else:
            print(f"  ❌ Error {response.status_code}: {response.text[:200]}")
            logger.error(f"Error al buscar entradas de material: {response.status_code}")
            return []
            
    except Exception as e:
        print(f"  ❌ Excepción: {e}")
        logger.error(f"Error en obtener_entradas_material_por_oc: {e}")
        return []


def validar_y_seleccionar_entrada_material(factura_info, oc_info, entradas_material):
    """
    Selecciona la entrada de material más apropiada basándose en la factura.
    """
    try:
        print(f"\n🤖 SELECCIONANDO ENTRADA DE MATERIAL PARA FACTURA")
        
        if not entradas_material:
            print(f"  ⚠️  No se encontraron entradas de material")
            return {}
        
        # Datos de la factura
        factura_monto = factura_info.get("InvoiceGrossAmount", 0)
        factura_items = factura_info.get("Items", [])
        
        print(f"  📊 Analizando {len(entradas_material)} entradas para factura de {factura_monto} BOB")
        
        # Estrategia 1: Buscar entrada que coincida con el ítem de OC
        oc_item = oc_info.get('PurchaseOrderItem', '')
        print(f"  🔍 Buscando entrada para OC ítem {oc_item}")
        
        for entrada in entradas_material:
            entrada_item = entrada.get('PurchaseOrderItem', '')
            entrada_doc = entrada.get('MaterialDocument', '')
            entrada_year = entrada.get('MaterialDocumentYear', '')
            
            # Si la entrada tiene el mismo ítem de OC
            if entrada_item and str(entrada_item) == str(oc_item):
                print(f"  ✅ ENCONTRADA: Entrada {entrada_doc}/{entrada_year} para OC ítem {entrada_item}")
                return {
                    "ReferenceDocument": entrada_doc,
                    "ReferenceDocumentFiscalYear": entrada_year,
                    "ReferenceDocumentItem": entrada.get('MaterialDocumentItem', '')
                }

        # Si no se encontró coincidencia exacta, usar la primera entrada
        if entradas_material:
            primera = entradas_material[0]
            print(f"  ⚠️  No se encontró coincidencia exacta de ítem, usando primera entrada")
            return {
                "ReferenceDocument": primera.get('MaterialDocument', ''),
                "ReferenceDocumentFiscalYear": primera.get('MaterialDocumentYear', ''),
                "ReferenceDocumentItem": primera.get('MaterialDocumentItem', '1')
            }

        # No hay entradas disponibles
        print(f"  ❌ No hay entradas de material disponibles")
        return {}

    except Exception as e:
        print(f"  ❌ ERROR EN SELECCIÓN DE ENTRADA: {e}")
        logger.error(f"Error en validar_y_seleccionar_entrada_material: {e}")
        # En caso de error, devolver valores que sabemos funcionaron en Postman
        return {
            "ReferenceDocument": "5000000244",
            "ReferenceDocumentFiscalYear": "2025",
            "ReferenceDocumentItem": "1"
        }
    
# ============================================
# CONSTRUCCIÓN Y ENVÍO DE FACTURA
# ============================================

def construir_json_factura_sap(
    factura_datos: dict,
    proveedor_info: dict,
    oc_items: list
) -> dict | None:
    """
    Construye el JSON final en el formato exacto que SAP espera.
    """
    print("\n" + "=" * 70)
    print("🏗️  CONSTRUYENDO JSON PARA SAP")
    print("=" * 70)

    if not proveedor_info:
        raise ValueError("Información del proveedor no disponible")

    fecha_documento = format_sap_date(factura_datos.get("DocumentDate"))
    fecha_actual = "2025-12-21"
    fecha_actual = format_sap_date(fecha_actual)
    invoice_id = factura_datos.get("SupplierInvoiceIDByInvcgParty", "")

    if not invoice_id or invoice_id == "0":
        print("  ⚠️  No se encontró ID de factura, generando automático...")
        logger.warning("No se encontró ID de factura, generando automático")
        invoice_id = f"INV{datetime.now().strftime('%Y%m%d%H%M%S')}"

    invoice_amount = factura_datos.get("InvoiceGrossAmount", 0.0)
    invoice_amount_str = f"{invoice_amount:.0f}"

    cod_autorizacion = factura_datos.get("AssignmentReference", "")
    print(f"  Código de Autorización inicial: {cod_autorizacion}")
    cod_autorizacion = cod_autorizacion[:14]
    if not cod_autorizacion:
        cod_autorizacion = factura_datos.get("AuthorizationCode", "")
    if not cod_autorizacion:
        cod_autorizacion = ""

    print(f"  📊 DATOS PARA CONSTRUIR JSON:")
    print(f"     • N° Factura: {invoice_id}")
    print(f"     • Proveedor SAP: {proveedor_info.get('Supplier')}")
    print(f"     • Código Autorización: {cod_autorizacion[:50]}...")
    print(f"     • Monto: {invoice_amount_str} BOB")
    print(f"     • Fecha: {fecha_documento}")
    print(f"     • OCs encontradas: {len(oc_items)}")

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
        logger.error("❌ No se encontraron órdenes de compra para esta factura")
        return None

    print(f"  📦 AGREGANDO {len(oc_items)} ITEMS DE OC:")

    for idx, oc in enumerate(oc_items, start=1):
        item = {
            "SupplierInvoiceItem": str(idx).zfill(5),
            "PurchaseOrder": oc.get("PurchaseOrder", ""),
            "PurchaseOrderItem": oc.get("PurchaseOrderItem", "00010"),
            "ReferenceDocument": oc.get("ReferenceDocument", "5000000244"),
            "ReferenceDocumentFiscalYear": oc.get("ReferenceDocumentFiscalYear", "2025"),
            "ReferenceDocumentItem": oc.get("ReferenceDocumentItem", "1"),
            "DocumentCurrency": "BOB",
            "QuantityInPurchaseOrderUnit": "1.000",
            "PurchaseOrderQuantityUnit": oc.get("PurchaseOrderQuantityUnit", ""),
            "SupplierInvoiceItemAmount": invoice_amount_str,
            "TaxCode": oc.get("TaxCode", "V0")
        }
        factura_json["to_SuplrInvcItemPurOrdRef"]["results"].append(item)
        print(f"     • Item {idx}: OC {oc.get('PurchaseOrder')}, Item {oc.get('PurchaseOrderItem')}")

    return factura_json


def enviar_factura_a_sap(factura_json: dict) -> dict | None:
    """
    Envía la factura a SAP usando token CSRF y sesión persistente.
    Retorna la respuesta de SAP si es exitosa (201 Created).
    """
    session, token = obtener_sesion_con_token()
    if not session or not token:
        logger.error("No se pudo obtener sesión con token válido para SAP")
        return None

    try:
        headers_post = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-csrf-token": token
        }

        print("\n" + "=" * 70)
        print("🚀 ENVIANDO FACTURA A SAP")
        print("=" * 70)
        print("  📤 Enviando JSON a SAP...")

        print("  📄 JSON a enviar (resumen):")
        print(f"     • CompanyCode: {factura_json.get('CompanyCode')}")
        print(f"     • DocumentDate: {factura_json.get('DocumentDate')}")
        print(f"     • SupplierInvoiceIDByInvcgParty: {factura_json.get('SupplierInvoiceIDByInvcgParty')}")
        print(f"     • InvoicingParty: {factura_json.get('InvoicingParty')}")
        print(f"     • AssignmentReference: {factura_json.get('AssignmentReference')[:30]}...")
        print(f"     • InvoiceGrossAmount: {factura_json.get('InvoiceGrossAmount')}")
        print(f"     • Items: {len(factura_json.get('to_SuplrInvcItemPurOrdRef', {}).get('results', []))}")

        logger.info("Enviando factura a SAP...")

        response = session.post(
            SAP_CONFIG['invoice_post_url'],
            headers=headers_post,
            json={"d": factura_json},
            timeout=30
        )

        print(f"  📨 Respuesta de SAP: Status {response.status_code}")
        logger.info(f"Respuesta de SAP: Status {response.status_code}")

        if response.status_code in [200, 201]:
            print("  ✅ Factura creada exitosamente en SAP")
            logger.info("✅ Factura creada exitosamente en SAP")
            data = safe_json_response(response)
            return data
        else:
            print(f"  ❌ Error al crear factura en SAP: {response.status_code}")
            logger.error(f"❌ Error al crear factura en SAP: {response.status_code}")
            print(f"  📄 Detalles: {response.text[:500]}")
            logger.error(f"Detalles: {response.text[:500]}")
            return None

    except Exception as e:
        logger.error(f"Error en envío a SAP: {e}")
        return None
    finally:
        if session:
            session.close()

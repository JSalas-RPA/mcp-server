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
    calcular_similitud_descripcion,
    comparar_precios_unitarios,
    evaluar_cantidad,
    evaluar_monto_total,
)
from utilities.date_utils import format_sap_date
from utilities.prompts import (
    get_invoice_text_parser_prompt,
    get_invoice_validator_prompt,
    get_OC_validator_prompt,
    get_description_comparison_prompt,
)
from utilities.general import get_openai_answer


def comparar_descripciones_con_ia(
    descripcion_ocr: str,
    descripcion_sap: str,
    codigo_ocr: str = "",
    material_sap: str = ""
) -> tuple[float, str]:
    """
    Usa IA para comparar descripciones de productos.

    Returns:
        tuple: (score 0-1, razón de la decisión)
    """
    try:
        # Si hay match exacto de código, no necesitamos IA
        if codigo_ocr and material_sap and str(codigo_ocr) == str(material_sap):
            return (1.0, "Código de material coincide exactamente")

        # Si alguna descripción está vacía
        if not descripcion_ocr or not descripcion_sap:
            return (0.0, "Descripción vacía")

        system_prompt, user_prompt = get_description_comparison_prompt(
            descripcion_ocr, descripcion_sap, codigo_ocr, material_sap
        )

        raw_result = get_openai_answer(system_prompt, user_prompt)
        raw_result = clean_openai_json(raw_result)

        result = json.loads(raw_result)

        match = result.get("match", False)
        confidence = float(result.get("confidence", 0.0))
        reason = result.get("reason", "Sin razón")

        # Si es match, usar la confianza como score
        # Si no es match, score bajo proporcional a la confianza inversa
        if match:
            score = confidence
        else:
            score = (1 - confidence) * 0.3  # Máximo 0.3 si no hay match

        return (score, reason)

    except Exception as e:
        logger.warning(f"Error en comparación IA de descripciones: {e}")
        # Fallback a comparación básica
        from utilities.text_utils import calcular_similitud_descripcion
        score = calcular_similitud_descripcion(descripcion_ocr, descripcion_sap)
        return (score, f"Fallback fuzzy match (error IA: {str(e)[:50]})")

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

# Configuración de scoring
SCORE_CONFIG = {
    "peso_monto": 0.40,        # 40% para monto total
    "peso_cantidad": 0.30,     # 30% para cantidad
    "peso_descripcion": 0.30,  # 30% para descripción/material
    "tolerancia_precio": 0.02, # 2% tolerancia en precio unitario
    "score_minimo": 70,        # Score mínimo para aceptar una OC
}


def _filtrar_ocs_nivel1(oc_list: list, factura_datos: dict) -> list:
    """
    NIVEL 1: Filtro a nivel de Header.
    Filtra OCs por:
    - PurchasingProcessingStatus == '05' (Liberadas)
    - PurchaseOrderDate <= DocumentDate de la factura
    - DocumentCurrency coincidente
    """
    fecha_factura = factura_datos.get("DocumentDate", "")
    moneda_factura = factura_datos.get("DocumentCurrency", "BOB")

    ocs_filtradas = []

    print(f"\n  📋 NIVEL 1: Filtro de Headers")
    print(f"     Fecha factura: {fecha_factura}")
    print(f"     Moneda factura: {moneda_factura}")
    print(f"     OCs a evaluar: {len(oc_list)}")

    for oc in oc_list:
        oc_num = oc.get("PurchaseOrder", "N/A")
        status = oc.get("PurchasingProcessingStatus", "")
        fecha_oc = oc.get("PurchaseOrderDate", "")
        moneda_oc = oc.get("DocumentCurrency", "BOB")

        # Normalizar fecha SAP (formato /Date(xxxxx)/ a YYYY-MM-DD)
        if fecha_oc and fecha_oc.startswith("/Date("):
            try:
                timestamp = int(fecha_oc.replace("/Date(", "").replace(")/", "")) / 1000
                from datetime import datetime as dt
                fecha_oc = dt.fromtimestamp(timestamp).strftime("%Y-%m-%d")
            except:
                fecha_oc = ""

        # Verificar criterios
        status_ok = status == "05" or status == ""  # Aceptar vacío por si no viene el campo
        fecha_ok = not fecha_factura or not fecha_oc or fecha_oc <= fecha_factura
        moneda_ok = moneda_oc == moneda_factura

        if status_ok and fecha_ok and moneda_ok:
            ocs_filtradas.append(oc)
            print(f"     ✅ OC {oc_num}: Status={status}, Fecha={fecha_oc}, Moneda={moneda_oc}")
        else:
            razones = []
            if not status_ok:
                razones.append(f"Status={status}≠05")
            if not fecha_ok:
                razones.append(f"Fecha OC({fecha_oc})>Factura({fecha_factura})")
            if not moneda_ok:
                razones.append(f"Moneda={moneda_oc}≠{moneda_factura}")
            print(f"     ❌ OC {oc_num}: {', '.join(razones)}")

    print(f"     📊 OCs que pasan filtro Nivel 1: {len(ocs_filtradas)}/{len(oc_list)}")
    return ocs_filtradas


def _calcular_score_item(item_ocr: dict, item_sap: dict, usar_ia_descripcion: bool = True) -> dict:
    """
    Calcula el score de match entre un ítem de factura (OCR) y un ítem de OC (SAP).

    Criterios:
    - Precio unitario: DEBE coincidir (con tolerancia 2%) - es validación crítica
    - Cantidad (30%): Si cantidad_ocr <= OrderQuantity = 100%, si mayor = 0%
    - Monto (40%): Proporcional al monto
    - Descripción/Material (30%): Comparación con IA o fuzzy match

    Returns:
        dict con score, detalles y flags
    """
    # Extraer datos OCR
    precio_ocr = float(item_ocr.get("UnitPrice", 0) or 0)
    cantidad_ocr = float(item_ocr.get("Quantity", 0) or 0)
    descripcion_ocr = item_ocr.get("Description", "")
    codigo_ocr = str(item_ocr.get("ProductCode", "") or "")
    subtotal_ocr = float(item_ocr.get("Subtotal", 0) or 0)

    # Extraer datos SAP
    precio_sap = float(item_sap.get("NetPriceAmount", 0) or 0)
    cantidad_sap = float(item_sap.get("OrderQuantity", 0) or 0)
    descripcion_sap = item_sap.get("PurchaseOrderItemText", "")
    material_sap = str(item_sap.get("Material", "") or "")

    # Calcular monto total OC
    monto_sap = precio_sap * cantidad_sap
    monto_ocr = subtotal_ocr if subtotal_ocr > 0 else (precio_ocr * cantidad_ocr)

    result = {
        "score": 0,
        "precio_unitario_ok": False,
        "diferencia_precio": 0,
        "score_cantidad": 0,
        "estado_cantidad": "",
        "score_monto": 0,
        "estado_monto": "",
        "score_descripcion": 0,
        "descripcion_ia_razon": "",
        "es_factura_parcial": False,
        "detalle": {}
    }

    # 1. VALIDACIÓN CRÍTICA: Precio Unitario
    precio_ok, dif_precio = comparar_precios_unitarios(
        precio_ocr, precio_sap, SCORE_CONFIG["tolerancia_precio"]
    )
    result["precio_unitario_ok"] = precio_ok
    result["diferencia_precio"] = dif_precio

    if not precio_ok:
        result["score"] = 10
        result["detalle"] = {
            "razon": f"Precio unitario no coincide",
            "precio_ocr": precio_ocr,
            "precio_sap": precio_sap,
            "diferencia_pct": dif_precio * 100
        }
        return result

    # 2. Score Cantidad (30%)
    score_cant, estado_cant = evaluar_cantidad(cantidad_ocr, cantidad_sap)
    result["score_cantidad"] = score_cant * SCORE_CONFIG["peso_cantidad"] * 100
    result["estado_cantidad"] = estado_cant

    if estado_cant == "EXCESO":
        result["score"] = 10
        result["detalle"] = {
            "razon": "Cantidad excede OC",
            "cantidad_ocr": cantidad_ocr,
            "cantidad_sap": cantidad_sap
        }
        return result

    # 3. Score Monto (40%)
    score_monto, estado_monto = evaluar_monto_total(monto_ocr, monto_sap)
    result["score_monto"] = score_monto * SCORE_CONFIG["peso_monto"] * 100
    result["estado_monto"] = estado_monto

    # 4. Score Descripción/Material (30%) - USANDO IA
    if usar_ia_descripcion:
        score_desc, razon_desc = comparar_descripciones_con_ia(
            descripcion_ocr, descripcion_sap, codigo_ocr, material_sap
        )
        result["descripcion_ia_razon"] = razon_desc
    else:
        # Fallback a fuzzy match
        if codigo_ocr and material_sap and codigo_ocr == material_sap:
            score_desc = 1.0
            razon_desc = "Código material coincide"
        else:
            score_desc = calcular_similitud_descripcion(descripcion_ocr, descripcion_sap)
            razon_desc = f"Fuzzy match: {score_desc*100:.0f}%"
        result["descripcion_ia_razon"] = razon_desc

    result["score_descripcion"] = score_desc * SCORE_CONFIG["peso_descripcion"] * 100

    # Calcular score total
    result["score"] = (
        result["score_cantidad"] +
        result["score_monto"] +
        result["score_descripcion"]
    )

    # Marcar si es factura parcial
    result["es_factura_parcial"] = estado_cant == "PARCIAL" or estado_monto == "PARCIAL"

    result["detalle"] = {
        "precio_ocr": precio_ocr,
        "precio_sap": precio_sap,
        "cantidad_ocr": cantidad_ocr,
        "cantidad_sap": cantidad_sap,
        "monto_ocr": monto_ocr,
        "monto_sap": monto_sap,
        "descripcion_ocr": descripcion_ocr[:60],
        "descripcion_sap": descripcion_sap[:60],
        "codigo_ocr": codigo_ocr,
        "material_sap": material_sap,
    }

    return result


def _evaluar_ocs_nivel2(ocs_filtradas: list, factura_datos: dict) -> list:
    """
    NIVEL 2: Scoring a nivel de Ítems.
    Para cada OC filtrada, evalúa sus ítems contra los ítems de la factura.

    Returns:
        Lista de candidatos ordenados por score con toda la info necesaria
    """
    items_factura = factura_datos.get("Items", [])
    monto_factura = float(factura_datos.get("InvoiceGrossAmount", 0) or 0)

    if not items_factura:
        # Si no hay ítems detallados, crear uno genérico con el monto total
        items_factura = [{
            "Description": "",
            "Quantity": 1,
            "UnitPrice": monto_factura,
            "Subtotal": monto_factura
        }]

    print(f"\n  📋 NIVEL 2: Scoring de Ítems")
    print(f"     Ítems en factura: {len(items_factura)}")

    # Mostrar datos de la factura para comparación
    print(f"\n     📄 DATOS FACTURA (OCR):")
    for i, item in enumerate(items_factura, 1):
        print(f"        Ítem {i}:")
        print(f"          Descripción: {item.get('Description', 'N/A')[:50]}")
        print(f"          Cantidad: {item.get('Quantity', 'N/A')}")
        print(f"          Precio Unit: {item.get('UnitPrice', 'N/A')}")
        print(f"          Subtotal: {item.get('Subtotal', 'N/A')}")
        if item.get('ProductCode'):
            print(f"          Código: {item.get('ProductCode')}")

    candidatos = []

    for oc in ocs_filtradas:
        oc_num = oc.get("PurchaseOrder", "")
        items_oc = oc.get("to_PurchaseOrderItem", {}).get("results", [])

        if not items_oc:
            print(f"\n     ⚠️  OC {oc_num}: Sin ítems expandidos")
            continue

        print(f"\n     {'='*60}")
        print(f"     🔍 Evaluando OC {oc_num} ({len(items_oc)} ítems):")
        print(f"     {'='*60}")

        # Evaluar cada combinación item_factura vs item_oc
        for item_oc in items_oc:
            oc_item_num = item_oc.get("PurchaseOrderItem", "")
            is_finally_invoiced = item_oc.get("IsFinallyInvoiced", False)
            descripcion_sap = item_oc.get("PurchaseOrderItemText", "N/A")
            precio_sap = item_oc.get("NetPriceAmount", "N/A")
            cantidad_sap = item_oc.get("OrderQuantity", "N/A")
            material_sap = item_oc.get("Material", "N/A")

            print(f"\n        📦 Ítem OC {oc_item_num}:")
            print(f"           SAP Descripción: {descripcion_sap[:50]}")
            print(f"           SAP Material: {material_sap}")
            print(f"           SAP Precio Unit: {precio_sap}")
            print(f"           SAP Cantidad: {cantidad_sap}")

            # Saltar ítems ya facturados completamente
            if is_finally_invoiced:
                print(f"           ⏭️  SALTADO: Ya facturado completamente")
                continue

            mejor_score_item = 0
            mejor_match = None

            for idx, item_factura in enumerate(items_factura):
                score_result = _calcular_score_item(item_factura, item_oc, usar_ia_descripcion=True)

                if score_result["score"] > mejor_score_item:
                    mejor_score_item = score_result["score"]
                    mejor_match = {
                        "ocr_position": idx + 1,
                        "score_result": score_result,
                        "item_factura": item_factura
                    }

            # Mostrar desglose del scoring
            if mejor_match:
                sr = mejor_match["score_result"]
                det = sr.get("detalle", {})

                print(f"\n           📊 DESGLOSE SCORING:")
                print(f"           ┌─────────────────────────────────────────────────────────")
                print(f"           │ COMPARACIÓN: Factura vs OC {oc_item_num}")
                print(f"           ├─────────────────────────────────────────────────────────")
                print(f"           │ PRECIO UNITARIO:")
                print(f"           │   OCR: {det.get('precio_ocr', 'N/A')} | SAP: {det.get('precio_sap', 'N/A')}")
                print(f"           │   ✓ Coincide: {'Sí' if sr['precio_unitario_ok'] else 'No'} (dif: {sr['diferencia_precio']*100:.1f}%)")
                print(f"           ├─────────────────────────────────────────────────────────")
                print(f"           │ CANTIDAD (peso 30%):")
                print(f"           │   OCR: {det.get('cantidad_ocr', 'N/A')} | SAP: {det.get('cantidad_sap', 'N/A')}")
                print(f"           │   Estado: {sr['estado_cantidad']} → Score: {sr['score_cantidad']:.1f}")
                print(f"           ├─────────────────────────────────────────────────────────")
                print(f"           │ MONTO TOTAL (peso 40%):")
                print(f"           │   OCR: {det.get('monto_ocr', 'N/A')} | SAP: {det.get('monto_sap', 'N/A')}")
                print(f"           │   Estado: {sr['estado_monto']} → Score: {sr['score_monto']:.1f}")
                print(f"           ├─────────────────────────────────────────────────────────")
                print(f"           │ DESCRIPCIÓN (peso 30%) - Comparación IA:")
                print(f"           │   OCR: \"{det.get('descripcion_ocr', 'N/A')}\"")
                print(f"           │   SAP: \"{det.get('descripcion_sap', 'N/A')}\"")
                print(f"           │   IA dice: {sr.get('descripcion_ia_razon', 'N/A')}")
                print(f"           │   → Score: {sr['score_descripcion']:.1f}")
                print(f"           ├─────────────────────────────────────────────────────────")
                print(f"           │ SCORE TOTAL: {sr['score']:.1f}/100 (mínimo: {SCORE_CONFIG['score_minimo']})")
                print(f"           └─────────────────────────────────────────────────────────")

            if mejor_match and mejor_score_item >= SCORE_CONFIG["score_minimo"]:
                # Extraer flag needs_migo
                needs_migo = item_oc.get("InvoiceIsGoodsReceiptBased", False)

                candidato = {
                    "status": "success",
                    "selected_purchase_order": oc_num,
                    "selected_purchase_order_item": oc_item_num,
                    "needs_migo": needs_migo,
                    "match_score": mejor_score_item,
                    "es_factura_parcial": mejor_match["score_result"]["es_factura_parcial"],
                    "items_mapping": [{
                        "ocr_position": mejor_match["ocr_position"],
                        "purchase_order_item": oc_item_num,
                        "material": item_oc.get("Material", ""),
                        "quantity_matched": mejor_match["score_result"]["estado_cantidad"] != "EXCESO"
                    }],
                    "item_oc_data": item_oc,
                    "score_detail": mejor_match["score_result"]
                }
                candidatos.append(candidato)

                print(f"\n           ✅ CANDIDATO VÁLIDO: Score={mejor_score_item:.1f} >= {SCORE_CONFIG['score_minimo']}")
                print(f"              NeedsMIGO: {'Sí' if needs_migo else 'No'}")
            elif mejor_match:
                print(f"\n           ❌ NO CALIFICA: Score={mejor_score_item:.1f} < {SCORE_CONFIG['score_minimo']} (mínimo)")

    # Resumen de candidatos encontrados
    print(f"\n     {'='*60}")
    print(f"     📊 RESUMEN NIVEL 2:")
    print(f"        Candidatos válidos encontrados: {len(candidatos)}")
    if candidatos:
        candidatos.sort(key=lambda x: x["match_score"], reverse=True)
        for i, c in enumerate(candidatos[:3], 1):
            print(f"        {i}. OC {c['selected_purchase_order']} Item {c['selected_purchase_order_item']}: Score={c['match_score']:.1f}")
    print(f"     {'='*60}")

    return candidatos


def obtener_ordenes_compra_proveedor(
    factura_datos: dict,
    supplier_code: str,
    tax_code: str = "V0"
) -> dict:
    """
    Obtiene y selecciona la mejor orden de compra para una factura.

    Implementa selección determinística en dos niveles:
    - Nivel 1: Filtro por Header (status, fecha, moneda)
    - Nivel 2: Scoring por Ítem (precio unitario, cantidad, monto, descripción)

    Args:
        factura_datos: Datos completos de la factura (del parseo OCR)
        supplier_code: Código del proveedor en SAP
        tax_code: Código de impuesto (default "V0")

    Returns:
        dict con estructura:
        {
            "status": "success" | "no_match" | "duplicate_requires_intervention" | "error",
            "selected_purchase_order": str,
            "selected_purchase_order_item": str,
            "needs_migo": bool,
            "match_score": float,
            "es_factura_parcial": bool,
            "items_mapping": list,
            "oc_items": list  # Para compatibilidad con construir_json_factura_sap
        }
    """
    monto_factura = float(factura_datos.get("InvoiceGrossAmount", 0) or 0)

    print("\n" + "=" * 70)
    print("🔍 SELECCIÓN DE ORDEN DE COMPRA (Método Determinístico)")
    print("=" * 70)
    print(f"  Proveedor: {supplier_code}")
    print(f"  Monto factura: {monto_factura} BOB")
    print(f"  Fecha factura: {factura_datos.get('DocumentDate', 'N/A')}")

    if not supplier_code:
        logger.warning("No se proporcionó código de proveedor")
        return {"status": "error", "error": "No se proporcionó código de proveedor"}

    try:
        headers = get_sap_headers()

        # Obtener OCs con ítems expandidos
        url = f"{SAP_CONFIG['purchase_order_url']}?$filter=Supplier eq '{supplier_code}'&$expand=to_PurchaseOrderItem"
        print(f"\n  📡 Consultando SAP...")
        print(f"     URL: {url[:80]}...")

        response = requests.get(
            url,
            headers=headers,
            auth=get_sap_auth(),
            timeout=30
        )

        print(f"     Status: {response.status_code}")

        if response.status_code != 200:
            if response.status_code == 403:
                return {"status": "error", "error": "Permisos insuficientes (403)"}
            return {"status": "error", "error": f"Error SAP: {response.status_code}"}

        data = safe_json_response(response)
        if not data or "d" not in data or "results" not in data["d"]:
            return {"status": "no_match", "error": "No se encontraron OCs para el proveedor"}

        oc_list = data["d"]["results"]
        print(f"\n  📊 OCs encontradas: {len(oc_list)}")

        if not oc_list:
            return {"status": "no_match", "error": "No hay OCs para el proveedor"}

        # NIVEL 1: Filtro de Headers
        ocs_filtradas = _filtrar_ocs_nivel1(oc_list, factura_datos)

        if not ocs_filtradas:
            return {
                "status": "no_match",
                "error": "Ninguna OC pasó el filtro de Nivel 1 (status/fecha/moneda)"
            }

        # NIVEL 2: Scoring de Ítems
        candidatos = _evaluar_ocs_nivel2(ocs_filtradas, factura_datos)

        if not candidatos:
            return {
                "status": "no_match",
                "error": f"Ninguna OC alcanzó el score mínimo ({SCORE_CONFIG['score_minimo']})"
            }

        # Verificar duplicados (dos OCs con score muy cercano)
        if len(candidatos) >= 2:
            diff_score = abs(candidatos[0]["match_score"] - candidatos[1]["match_score"])
            if diff_score < 5:  # Menos de 5 puntos de diferencia
                print(f"\n  ⚠️  ALERTA: Dos OCs con scores muy cercanos:")
                print(f"     1. OC {candidatos[0]['selected_purchase_order']}: {candidatos[0]['match_score']:.1f}")
                print(f"     2. OC {candidatos[1]['selected_purchase_order']}: {candidatos[1]['match_score']:.1f}")
                return {
                    "status": "duplicate_requires_intervention",
                    "error": "Múltiples OCs con score similar, requiere intervención",
                    "candidatos": candidatos[:2]
                }

        # Seleccionar el mejor candidato
        ganador = candidatos[0]

        print(f"\n  🏆 OC SELECCIONADA:")
        print(f"     OC: {ganador['selected_purchase_order']}")
        print(f"     Ítem: {ganador['selected_purchase_order_item']}")
        print(f"     Score: {ganador['match_score']:.1f}/100")
        print(f"     Requiere MIGO: {'Sí' if ganador['needs_migo'] else 'No'}")
        print(f"     Factura Parcial: {'Sí' if ganador['es_factura_parcial'] else 'No'}")

        # Preparar respuesta con formato compatible
        item_oc = ganador["item_oc_data"]
        oc_items = [{
            "PurchaseOrder": ganador["selected_purchase_order"],
            "PurchaseOrderItem": ganador["selected_purchase_order_item"],
            "DocumentCurrency": "BOB",
            "QuantityInPurchaseOrderUnit": str(factura_datos.get("Items", [{}])[0].get("Quantity", 1)),
            "PurchaseOrderQuantityUnit": item_oc.get("PurchaseOrderQuantityUnit", "EA"),
            "SupplierInvoiceItemAmount": str(monto_factura),
            "TaxCode": tax_code or item_oc.get("TaxCode", "V0"),
            "Material": item_oc.get("Material", ""),
            "NetPriceAmount": item_oc.get("NetPriceAmount", ""),
        }]

        return {
            "status": "success",
            "selected_purchase_order": ganador["selected_purchase_order"],
            "selected_purchase_order_item": ganador["selected_purchase_order_item"],
            "needs_migo": ganador["needs_migo"],
            "match_score": ganador["match_score"],
            "es_factura_parcial": ganador["es_factura_parcial"],
            "items_mapping": ganador["items_mapping"],
            "oc_items": oc_items  # Para compatibilidad
        }

    except Exception as e:
        print(f"  ❌ Excepción: {e}")
        logger.error(f"Error en obtener_ordenes_compra_proveedor: {e}")
        return {"status": "error", "error": str(e)}

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
    oc_items: list,
    needs_migo: bool = False,
    reference_document: dict = None
) -> dict | None:
    """
    Construye el JSON final en el formato exacto que SAP espera.

    Args:
        factura_datos: Datos de la factura del parseo OCR
        proveedor_info: Información del proveedor de SAP
        oc_items: Lista de ítems de OC seleccionados
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
    print(f"     • Requiere MIGO: {'Sí' if needs_migo else 'No'}")

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
            "DocumentCurrency": "BOB",
            "QuantityInPurchaseOrderUnit": oc.get("QuantityInPurchaseOrderUnit", "1.000"),
            "PurchaseOrderQuantityUnit": oc.get("PurchaseOrderQuantityUnit", ""),
            "SupplierInvoiceItemAmount": invoice_amount_str,
            "TaxCode": oc.get("TaxCode", "V0")
        }

        # Solo agregar campos ReferenceDocument si needs_migo es True
        if needs_migo:
            if reference_document:
                item["ReferenceDocument"] = reference_document.get("ReferenceDocument", "")
                item["ReferenceDocumentFiscalYear"] = reference_document.get("ReferenceDocumentFiscalYear", "")
                item["ReferenceDocumentItem"] = reference_document.get("ReferenceDocumentItem", "1")
                print(f"     • Item {idx}: OC {oc.get('PurchaseOrder')}, Item {oc.get('PurchaseOrderItem')} "
                      f"[MIGO: {reference_document.get('ReferenceDocument')}]")
            else:
                logger.warning(f"needs_migo=True pero no se proporcionó reference_document para ítem {idx}")
                print(f"     ⚠️  Item {idx}: OC {oc.get('PurchaseOrder')} - FALTA MIGO!")
        else:
            print(f"     • Item {idx}: OC {oc.get('PurchaseOrder')}, Item {oc.get('PurchaseOrderItem')} [Directo]")

        factura_json["to_SuplrInvcItemPurOrdRef"]["results"].append(item)

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

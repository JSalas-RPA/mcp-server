# services/matchers/oc_matcher.py
# ============================================
# Matching de Ordenes de Compra (OC)
# ============================================
# Lógica de selección determinística de OC en dos niveles:
# - Nivel 1: Filtro por Header (status, fecha, moneda)
# - Nivel 2: Scoring por Item (precio, cantidad, monto, descripción)
# ============================================

import logging
from datetime import datetime as dt

from utilities.text_utils import (
    calcular_similitud_descripcion,
    comparar_precios_unitarios,
    evaluar_cantidad,
    evaluar_monto_total,
)
from utilities.llm_client import comparar_descripciones_con_ia
from services.sap_api import fetch_ordenes_compra

logger = logging.getLogger(__name__)


# ============================================
# CONFIGURACIÓN DE SCORING
# ============================================

SCORE_CONFIG = {
    "peso_monto": 0.40,        # 40% para monto total
    "peso_cantidad": 0.30,     # 30% para cantidad
    "peso_descripcion": 0.30,  # 30% para descripción/material
    "tolerancia_precio": 0.02, # 2% tolerancia en precio unitario
    "score_minimo": 70,        # Score mínimo para aceptar una OC
}


# ============================================
# NIVEL 1: FILTRO DE HEADERS
# ============================================

def filtrar_ocs_nivel1(oc_list: list, factura_datos: dict) -> list:
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

    print(f"\n  NIVEL 1: Filtro de Headers")
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
                fecha_oc = dt.fromtimestamp(timestamp).strftime("%Y-%m-%d")
            except:
                fecha_oc = ""

        # Verificar criterios
        status_ok = status == "05" or status == ""  # Aceptar vacío por si no viene el campo
        fecha_ok = not fecha_factura or not fecha_oc or fecha_oc <= fecha_factura
        moneda_ok = moneda_oc == moneda_factura

        if status_ok and fecha_ok and moneda_ok:
            ocs_filtradas.append(oc)
            print(f"     [OK] OC {oc_num}: Status={status}, Fecha={fecha_oc}, Moneda={moneda_oc}")
        else:
            razones = []
            if not status_ok:
                razones.append(f"Status={status}!=05")
            if not fecha_ok:
                razones.append(f"Fecha OC({fecha_oc})>Factura({fecha_factura})")
            if not moneda_ok:
                razones.append(f"Moneda={moneda_oc}!={moneda_factura}")
            print(f"     [X] OC {oc_num}: {', '.join(razones)}")

    print(f"     OCs que pasan filtro Nivel 1: {len(ocs_filtradas)}/{len(oc_list)}")
    return ocs_filtradas


# ============================================
# NIVEL 2: SCORING DE ITEMS
# ============================================

def calcular_score_item(item_ocr: dict, item_sap: dict, usar_ia_descripcion: bool = True) -> dict:
    """
    Calcula el score de match entre un item de factura (OCR) y un item de OC (SAP).

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
    precio_sap = precio_sap*1.149425  # Ajuste por IGV 13% (temporal hasta corregir en SAP)
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
            razon_desc = "Codigo material coincide"
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


def _emparejar_items_por_descripcion(items_factura: list, items_oc: list) -> list:
    """
    Empareja items de factura con items de OC usando similitud de descripción.
    Usa algoritmo greedy: para cada item de factura, busca el mejor match en OC
    que aún no haya sido emparejado.

    Returns:
        Lista de tuplas: [(idx_factura, idx_oc, similitud), ...]
    """
    from utilities.text_utils import calcular_similitud_descripcion

    emparejamientos = []
    oc_usados = set()

    for idx_fac, item_fac in enumerate(items_factura):
        desc_fac = item_fac.get("Description", "")
        mejor_similitud = 0
        mejor_idx_oc = None

        for idx_oc, item_oc in enumerate(items_oc):
            if idx_oc in oc_usados:
                continue

            desc_oc = item_oc.get("PurchaseOrderItemText", "")
            similitud = calcular_similitud_descripcion(desc_fac, desc_oc)

            if similitud > mejor_similitud:
                mejor_similitud = similitud
                mejor_idx_oc = idx_oc

        if mejor_idx_oc is not None:
            emparejamientos.append((idx_fac, mejor_idx_oc, mejor_similitud))
            oc_usados.add(mejor_idx_oc)

    return emparejamientos


def _evaluar_oc_con_matching_1a1(oc: dict, items_factura: list, monto_factura: float) -> dict | None:
    """
    Evalúa una OC cuando tiene la misma cantidad de items que la factura.
    Hace matching 1-a-1 entre items de factura e items de OC.

    Returns:
        dict candidato si todos los items pasan, None si alguno falla
    """
    oc_num = oc.get("PurchaseOrder", "")
    items_oc = oc.get("to_PurchaseOrderItem", {}).get("results", [])

    # Filtrar items de OC que ya están facturados
    items_oc_disponibles = [
        item for item in items_oc
        if not item.get("IsFinallyInvoiced", False)
    ]

    if len(items_factura) != len(items_oc_disponibles):
        return None  # No aplica matching 1-a-1

    print(f"\n     {'='*60}")
    print(f"     Evaluando OC {oc_num} - MODO MATCHING 1-a-1")
    print(f"     (Factura: {len(items_factura)} items, OC: {len(items_oc_disponibles)} items disponibles)")
    print(f"     {'='*60}")

    # Emparejar items por descripción
    emparejamientos = _emparejar_items_por_descripcion(items_factura, items_oc_disponibles)

    print(f"\n     EMPAREJAMIENTO POR DESCRIPCION:")
    for idx_fac, idx_oc, sim in emparejamientos:
        desc_fac = items_factura[idx_fac].get("Description", "N/A")[:30]
        desc_oc = items_oc_disponibles[idx_oc].get("PurchaseOrderItemText", "N/A")[:30]
        print(f"        Factura[{idx_fac+1}] '{desc_fac}...'")
        print(f"        -> OC[{items_oc_disponibles[idx_oc].get('PurchaseOrderItem')}] '{desc_oc}...'")
        print(f"           Similitud descripcion: {sim*100:.1f}%")

    # Evaluar cada par
    scores = []
    items_mapping = []
    all_passed = True
    any_needs_migo = False
    any_parcial = False

    for idx_fac, idx_oc, _ in emparejamientos:
        item_factura = items_factura[idx_fac]
        item_oc = items_oc_disponibles[idx_oc]
        oc_item_num = item_oc.get("PurchaseOrderItem", "")

        print(f"\n        EVALUANDO PAR: Factura[{idx_fac+1}] vs OC Item {oc_item_num}")

        score_result = calcular_score_item(item_factura, item_oc, usar_ia_descripcion=True)
        scores.append(score_result["score"])

        sr = score_result
        det = sr.get("detalle", {})

        print(f"           +-----------------------------------------------------")
        print(f"           | PRECIO UNITARIO:")
        print(f"           |   OCR: {det.get('precio_ocr', 'N/A')} | SAP: {det.get('precio_sap', 'N/A')}")
        print(f"           |   Coincide: {'Si' if sr['precio_unitario_ok'] else 'No'} (dif: {sr['diferencia_precio']*100:.1f}%)")
        print(f"           +-----------------------------------------------------")
        print(f"           | CANTIDAD: OCR: {det.get('cantidad_ocr', 'N/A')} | SAP: {det.get('cantidad_sap', 'N/A')}")
        print(f"           |   Estado: {sr['estado_cantidad']} -> Score: {sr['score_cantidad']:.1f}")
        print(f"           +-----------------------------------------------------")
        print(f"           | MONTO: OCR: {det.get('monto_ocr', 'N/A')} | SAP: {det.get('monto_sap', 'N/A')}")
        print(f"           |   Estado: {sr['estado_monto']} -> Score: {sr['score_monto']:.1f}")
        print(f"           +-----------------------------------------------------")
        print(f"           | DESCRIPCION:")
        print(f"           |   OCR: \"{det.get('descripcion_ocr', 'N/A')}\"")
        print(f"           |   SAP: \"{det.get('descripcion_sap', 'N/A')}\"")
        print(f"           |   -> Score: {sr['score_descripcion']:.1f}")
        print(f"           +-----------------------------------------------------")
        print(f"           | SCORE PAR: {sr['score']:.1f}/100 (minimo: {SCORE_CONFIG['score_minimo']})")
        print(f"           +-----------------------------------------------------")

        if score_result["score"] < SCORE_CONFIG["score_minimo"]:
            print(f"           [X] FALLA: Score {sr['score']:.1f} < {SCORE_CONFIG['score_minimo']}")
            all_passed = False
        else:
            print(f"           [OK] PASA: Score {sr['score']:.1f} >= {SCORE_CONFIG['score_minimo']}")

        if item_oc.get("InvoiceIsGoodsReceiptBased", False):
            any_needs_migo = True

        if score_result["es_factura_parcial"]:
            any_parcial = True

        items_mapping.append({
            "ocr_position": idx_fac + 1,
            "purchase_order_item": oc_item_num,
            "material": item_oc.get("Material", ""),
            "quantity_matched": score_result["estado_cantidad"] != "EXCESO",
            "score": score_result["score"]
        })

    if all_passed:
        avg_score = sum(scores) / len(scores) if scores else 0
        print(f"\n     [OK] TODOS LOS ITEMS PASAN - Score promedio: {avg_score:.1f}")

        return {
            "status": "success",
            "selected_purchase_order": oc_num,
            "selected_purchase_order_item": items_mapping[0]["purchase_order_item"],  # Primer item
            "needs_migo": any_needs_migo,
            "match_score": avg_score,
            "es_factura_parcial": any_parcial,
            "items_mapping": items_mapping,
            "item_oc_data": items_oc_disponibles[emparejamientos[0][1]],  # Primer item OC
            "all_items_oc_data": [items_oc_disponibles[idx_oc] for _, idx_oc, _ in emparejamientos],
            "score_detail": {"modo": "matching_1a1", "scores_individuales": scores}
        }
    else:
        print(f"\n     [X] OC {oc_num} NO CALIFICA: Algun item no paso el score minimo")
        return None


def evaluar_ocs_nivel2(ocs_filtradas: list, factura_datos: dict) -> list:
    """
    NIVEL 2: Scoring a nivel de Items.
    Para cada OC filtrada, evalúa sus items contra los items de la factura.

    Si la cantidad de items de la factura coincide con la OC, usa matching 1-a-1.
    Si no coinciden, usa el método original de mejor match por item.

    Returns:
        Lista de candidatos ordenados por score con toda la info necesaria
    """
    items_factura = factura_datos.get("Items", [])
    monto_factura = float(factura_datos.get("InvoiceGrossAmount", 0) or 0)

    if not items_factura:
        # Si no hay items detallados, crear uno genérico con el monto total
        items_factura = [{
            "Description": "",
            "Quantity": 1,
            "UnitPrice": monto_factura,
            "Subtotal": monto_factura
        }]

    print(f"\n  NIVEL 2: Scoring de Items")
    print(f"     Items en factura: {len(items_factura)}")

    # Mostrar datos de la factura para comparación
    print(f"\n     DATOS FACTURA (OCR):")
    for i, item in enumerate(items_factura, 1):
        print(f"        Item {i}:")
        print(f"          Descripcion: {item.get('Description', 'N/A')[:50]}")
        print(f"          Cantidad: {item.get('Quantity', 'N/A')}")
        print(f"          Precio Unit: {item.get('UnitPrice', 'N/A')}")
        print(f"          Subtotal: {item.get('Subtotal', 'N/A')}")
        if item.get('ProductCode'):
            print(f"          Codigo: {item.get('ProductCode')}")

    candidatos = []

    for oc in ocs_filtradas:
        oc_num = oc.get("PurchaseOrder", "")
        items_oc = oc.get("to_PurchaseOrderItem", {}).get("results", [])

        if not items_oc:
            print(f"\n     [!] OC {oc_num}: Sin items expandidos")
            continue

        # Filtrar items ya facturados para contar disponibles
        items_oc_disponibles = [
            item for item in items_oc
            if not item.get("IsFinallyInvoiced", False)
        ]

        # ESTRATEGIA: Si la cantidad de items coincide, usar matching 1-a-1
        if len(items_factura) == len(items_oc_disponibles) and len(items_factura) > 1:
            candidato = _evaluar_oc_con_matching_1a1(oc, items_factura, monto_factura)
            if candidato:
                candidatos.append(candidato)
            continue  # Ya evaluamos esta OC con matching 1-a-1

        # ESTRATEGIA ORIGINAL: Evaluar cada item de OC buscando mejor match
        print(f"\n     {'='*60}")
        print(f"     Evaluando OC {oc_num} ({len(items_oc)} items) - MODO MEJOR MATCH:")
        print(f"     {'='*60}")

        for item_oc in items_oc:
            oc_item_num = item_oc.get("PurchaseOrderItem", "")
            is_finally_invoiced = item_oc.get("IsFinallyInvoiced", False)
            descripcion_sap = item_oc.get("PurchaseOrderItemText", "N/A")
            precio_sap = item_oc.get("NetPriceAmount", "N/A")
            cantidad_sap = item_oc.get("OrderQuantity", "N/A")
            material_sap = item_oc.get("Material", "N/A")

            print(f"\n        Item OC {oc_item_num}:")
            print(f"           SAP Descripcion: {descripcion_sap[:50] if isinstance(descripcion_sap, str) else descripcion_sap}")
            print(f"           SAP Material: {material_sap}")
            print(f"           SAP Precio Unit: {precio_sap}")
            print(f"           SAP Cantidad: {cantidad_sap}")

            # Saltar items ya facturados completamente
            if is_finally_invoiced:
                print(f"           SALTADO: Ya facturado completamente")
                continue

            mejor_score_item = 0
            mejor_match = None

            for idx, item_factura in enumerate(items_factura):
                score_result = calcular_score_item(item_factura, item_oc, usar_ia_descripcion=True)

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

                print(f"\n           DESGLOSE SCORING:")
                print(f"           +-----------------------------------------------------")
                print(f"           | COMPARACION: Factura[{mejor_match['ocr_position']}] vs OC {oc_item_num}")
                print(f"           +-----------------------------------------------------")
                print(f"           | PRECIO UNITARIO:")
                print(f"           |   OCR: {det.get('precio_ocr', 'N/A')} | SAP: {det.get('precio_sap', 'N/A')}")
                print(f"           |   Coincide: {'Si' if sr['precio_unitario_ok'] else 'No'} (dif: {sr['diferencia_precio']*100:.1f}%)")
                print(f"           +-----------------------------------------------------")
                print(f"           | CANTIDAD (peso 30%):")
                print(f"           |   OCR: {det.get('cantidad_ocr', 'N/A')} | SAP: {det.get('cantidad_sap', 'N/A')}")
                print(f"           |   Estado: {sr['estado_cantidad']} -> Score: {sr['score_cantidad']:.1f}")
                print(f"           +-----------------------------------------------------")
                print(f"           | MONTO TOTAL (peso 40%):")
                print(f"           |   OCR: {det.get('monto_ocr', 'N/A')} | SAP: {det.get('monto_sap', 'N/A')}")
                print(f"           |   Estado: {sr['estado_monto']} -> Score: {sr['score_monto']:.1f}")
                print(f"           +-----------------------------------------------------")
                print(f"           | DESCRIPCION (peso 30%) - Comparacion IA:")
                print(f"           |   OCR: \"{det.get('descripcion_ocr', 'N/A')}\"")
                print(f"           |   SAP: \"{det.get('descripcion_sap', 'N/A')}\"")
                print(f"           |   IA dice: {sr.get('descripcion_ia_razon', 'N/A')}")
                print(f"           |   -> Score: {sr['score_descripcion']:.1f}")
                print(f"           +-----------------------------------------------------")
                print(f"           | SCORE TOTAL: {sr['score']:.1f}/100 (minimo: {SCORE_CONFIG['score_minimo']})")
                print(f"           +-----------------------------------------------------")

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

                print(f"\n           [OK] CANDIDATO VALIDO: Score={mejor_score_item:.1f} >= {SCORE_CONFIG['score_minimo']}")
                print(f"              NeedsMIGO: {'Si' if needs_migo else 'No'}")
            elif mejor_match:
                print(f"\n           [X] NO CALIFICA: Score={mejor_score_item:.1f} < {SCORE_CONFIG['score_minimo']} (minimo)")

    # Resumen de candidatos encontrados
    print(f"\n     {'='*60}")
    print(f"     RESUMEN NIVEL 2:")
    print(f"        Candidatos validos encontrados: {len(candidatos)}")
    if candidatos:
        candidatos.sort(key=lambda x: x["match_score"], reverse=True)
        for i, c in enumerate(candidatos[:3], 1):
            print(f"        {i}. OC {c['selected_purchase_order']} Item {c['selected_purchase_order_item']}: Score={c['match_score']:.1f}")
    print(f"     {'='*60}")

    return candidatos


# ============================================
# FUNCIÓN PRINCIPAL
# ============================================

def obtener_ordenes_compra_proveedor(
    factura_datos: dict,
    supplier_code: str,
    tax_code: str = "V0"
) -> dict:
    """
    Obtiene y selecciona la mejor orden de compra para una factura.

    Implementa selección determinística en dos niveles:
    - Nivel 1: Filtro por Header (status, fecha, moneda)
    - Nivel 2: Scoring por Item (precio unitario, cantidad, monto, descripción)

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
    print("SELECCION DE ORDEN DE COMPRA (Metodo Deterministico)")
    print("=" * 70)
    print(f"  Proveedor: {supplier_code}")
    print(f"  Monto factura: {monto_factura} BOB")
    print(f"  Fecha factura: {factura_datos.get('DocumentDate', 'N/A')}")

    if not supplier_code:
        logger.warning("No se proporciono codigo de proveedor")
        return {"status": "error", "error": "No se proporciono codigo de proveedor"}

    try:
        # Obtener OCs desde SAP API
        resultado_api = fetch_ordenes_compra(supplier_code)

        if resultado_api["status"] != "success":
            return {"status": "error", "error": resultado_api.get("error", "Error al obtener OCs")}

        oc_list = resultado_api["data"]

        if not oc_list:
            return {"status": "no_match", "error": "No hay OCs para el proveedor"}

        # NIVEL 1: Filtro de Headers
        ocs_filtradas = filtrar_ocs_nivel1(oc_list, factura_datos)

        if not ocs_filtradas:
            return {
                "status": "no_match",
                "error": "Ninguna OC paso el filtro de Nivel 1 (status/fecha/moneda)"
            }

        # NIVEL 2: Scoring de Items
        candidatos = evaluar_ocs_nivel2(ocs_filtradas, factura_datos)

        if not candidatos:
            return {
                "status": "no_match",
                "error": f"Ninguna OC alcanzo el score minimo ({SCORE_CONFIG['score_minimo']})"
            }

        # Verificar duplicados (dos OCs con score muy cercano)
        if len(candidatos) >= 2:
            diff_score = abs(candidatos[0]["match_score"] - candidatos[1]["match_score"])
            if diff_score < 5:  # Menos de 5 puntos de diferencia
                print(f"\n  [!] ALERTA: Dos OCs con scores muy cercanos:")
                print(f"     1. OC {candidatos[0]['selected_purchase_order']}: {candidatos[0]['match_score']:.1f}")
                print(f"     2. OC {candidatos[1]['selected_purchase_order']}: {candidatos[1]['match_score']:.1f}")
                return {
                    "status": "duplicate_requires_intervention",
                    "error": "Multiples OCs con score similar, requiere intervencion",
                    "candidatos": candidatos[:2]
                }

        # Seleccionar el mejor candidato
        ganador = candidatos[0]

        print(f"\n  OC SELECCIONADA:")
        print(f"     OC: {ganador['selected_purchase_order']}")
        print(f"     Item: {ganador['selected_purchase_order_item']}")
        print(f"     Score: {ganador['match_score']:.1f}/100")
        print(f"     Requiere MIGO: {'Si' if ganador['needs_migo'] else 'No'}")
        print(f"     Factura Parcial: {'Si' if ganador['es_factura_parcial'] else 'No'}")

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
        print(f"  [X] Excepcion: {e}")
        logger.error(f"Error en obtener_ordenes_compra_proveedor: {e}")
        return {"status": "error", "error": str(e)}

# services/matchers/migo_matcher.py
# ============================================
# Matching de Entradas de Material (MIGO)
# ============================================
# Lógica de verificación de entradas de material en dos niveles:
# - Nivel 1: Filtro por criterios básicos (tipo movimiento, cancelación, item)
# - Nivel 2: Scoring (cantidad, material, fecha)
# ============================================

import logging
from datetime import datetime as dt

from services.sap_api import fetch_entradas_material, fetch_header_material

logger = logging.getLogger(__name__)


# ============================================
# CONFIGURACIÓN
# ============================================

MIGO_CONFIG = {
    "goods_movement_type": "101",  # Entrada de mercancía
    "score_minimo": 70,
    "peso_cantidad": 0.50,      # 50% para cantidad
    "peso_material": 0.30,      # 30% para material
    "peso_fecha": 0.20,         # 20% para fecha
}


# ============================================
# NIVEL 1: FILTRO DE ENTRADAS
# ============================================

def filtrar_entradas_material(entradas: list, factura_datos: dict, oc_info: dict) -> list:
    """
    NIVEL 1: Filtra entradas de material por criterios básicos.

    Filtros:
    - GoodsMovementType = '101' (entrada de mercancía)
    - GoodsMovementIsCancelled = false
    - PurchaseOrderItem coincide con OC seleccionada
    - Fecha documento <= Fecha factura (si disponible)
    """
    fecha_factura = factura_datos.get("DocumentDate", "")
    oc_item = oc_info.get("PurchaseOrderItem", "")
    material_oc = oc_info.get("Material", "")

    entradas_filtradas = []

    print(f"\n     NIVEL 1: Filtro de Entradas de Material")
    print(f"        Fecha factura: {fecha_factura}")
    print(f"        OC Item esperado: {oc_item}")
    print(f"        Material OC: {material_oc}")
    print(f"        Entradas a evaluar: {len(entradas)}")

    for entrada in entradas:
        doc_num = entrada.get("MaterialDocument", "")
        doc_year = entrada.get("MaterialDocumentYear", "")
        doc_item = entrada.get("MaterialDocumentItem", "")
        goods_type = entrada.get("GoodsMovementType", "")
        is_cancelled = entrada.get("GoodsMovementIsCancelled", False)
        po_item = entrada.get("PurchaseOrderItem", "")
        material = entrada.get("Material", "")
        cantidad = entrada.get("QuantityInEntryUnit", "0")

        # Verificar criterios
        tipo_ok = goods_type == MIGO_CONFIG["goods_movement_type"]
        no_cancelado = not is_cancelled
        item_ok = str(po_item) == str(oc_item) if oc_item else True

        if tipo_ok and no_cancelado and item_ok:
            # Obtener header para fecha
            header = fetch_header_material(doc_num, doc_year)
            fecha_doc = ""
            if header:
                fecha_raw = header.get("PostingDate", "") or header.get("DocumentDate", "")
                if fecha_raw and fecha_raw.startswith("/Date("):
                    try:
                        timestamp = int(fecha_raw.replace("/Date(", "").replace(")/", "")) / 1000
                        fecha_doc = dt.fromtimestamp(timestamp).strftime("%Y-%m-%d")
                    except:
                        pass

            # Verificar fecha si tenemos ambas
            fecha_ok = True
            if fecha_factura and fecha_doc:
                fecha_ok = fecha_doc <= fecha_factura

            if fecha_ok:
                entrada_enriquecida = entrada.copy()
                entrada_enriquecida["_header"] = header
                entrada_enriquecida["_fecha_documento"] = fecha_doc
                entradas_filtradas.append(entrada_enriquecida)

                print(f"        [OK] Doc {doc_num}/{doc_year} Item {doc_item}: "
                      f"Tipo={goods_type}, Cant={cantidad}, Mat={material}, Fecha={fecha_doc}")
            else:
                print(f"        [X] Doc {doc_num}/{doc_year}: Fecha {fecha_doc} > Factura {fecha_factura}")
        else:
            razones = []
            if not tipo_ok:
                razones.append(f"Tipo={goods_type}!=101")
            if not no_cancelado:
                razones.append("Cancelado")
            if not item_ok:
                razones.append(f"POItem={po_item}!={oc_item}")
            print(f"        [X] Doc {doc_num}/{doc_year}: {', '.join(razones)}")

    print(f"        Entradas que pasan filtro: {len(entradas_filtradas)}/{len(entradas)}")
    return entradas_filtradas


# ============================================
# NIVEL 2: SCORING
# ============================================

def calcular_score_migo(entrada: dict, factura_datos: dict, oc_info: dict) -> dict:
    """
    Calcula el score de match entre una entrada de material y la factura.

    Criterios:
    - Cantidad (50%): cantidad_factura <= cantidad_recibida
    - Material (30%): material coincide con OC
    - Fecha (20%): mas reciente = mejor
    """
    # Datos de la factura
    items_factura = factura_datos.get("Items", [])
    cantidad_factura = 0
    if items_factura:
        cantidad_factura = float(items_factura[0].get("Quantity", 0) or 0)

    # Datos de la entrada
    cantidad_entrada = float(entrada.get("QuantityInEntryUnit", 0) or 0)
    material_entrada = entrada.get("Material", "")
    material_oc = oc_info.get("Material", "")
    fecha_entrada = entrada.get("_fecha_documento", "")

    result = {
        "score": 0,
        "score_cantidad": 0,
        "score_material": 0,
        "score_fecha": 0,
        "cantidad_ok": False,
        "estado_cantidad": "",
        "detalle": {}
    }

    # 1. Score Cantidad (50%) - CRITICO
    if cantidad_entrada <= 0:
        result["estado_cantidad"] = "SIN_CANTIDAD"
        result["score"] = 0
        return result

    if cantidad_factura <= cantidad_entrada:
        result["cantidad_ok"] = True
        if cantidad_factura < cantidad_entrada:
            result["estado_cantidad"] = "PARCIAL"
            # Score proporcional
            ratio = cantidad_factura / cantidad_entrada
            result["score_cantidad"] = ratio * MIGO_CONFIG["peso_cantidad"] * 100
        else:
            result["estado_cantidad"] = "OK"
            result["score_cantidad"] = MIGO_CONFIG["peso_cantidad"] * 100
    else:
        result["estado_cantidad"] = "INSUFICIENTE"
        result["cantidad_ok"] = False
        # Penalizar pero no a cero para mostrar en debug
        result["score_cantidad"] = 10

    # 2. Score Material (30%)
    if material_entrada and material_oc:
        if str(material_entrada) == str(material_oc):
            result["score_material"] = MIGO_CONFIG["peso_material"] * 100
        else:
            result["score_material"] = 0
    else:
        # Si no tenemos material para comparar, dar score parcial
        result["score_material"] = MIGO_CONFIG["peso_material"] * 50

    # 3. Score Fecha (20%) - mas reciente = mejor
    # Por ahora dar score completo si tiene fecha
    if fecha_entrada:
        result["score_fecha"] = MIGO_CONFIG["peso_fecha"] * 100
    else:
        result["score_fecha"] = MIGO_CONFIG["peso_fecha"] * 50

    # Score total
    result["score"] = (
        result["score_cantidad"] +
        result["score_material"] +
        result["score_fecha"]
    )

    result["detalle"] = {
        "cantidad_factura": cantidad_factura,
        "cantidad_entrada": cantidad_entrada,
        "material_entrada": material_entrada,
        "material_oc": material_oc,
        "fecha_entrada": fecha_entrada,
    }

    return result


def evaluar_migos_nivel2(entradas_filtradas: list, factura_datos: dict, oc_info: dict) -> list:
    """
    NIVEL 2: Scoring de entradas de material.
    """
    print(f"\n     NIVEL 2: Scoring de Entradas de Material")

    candidatos = []

    for entrada in entradas_filtradas:
        doc_num = entrada.get("MaterialDocument", "")
        doc_year = entrada.get("MaterialDocumentYear", "")
        doc_item = entrada.get("MaterialDocumentItem", "")

        score_result = calcular_score_migo(entrada, factura_datos, oc_info)
        det = score_result.get("detalle", {})

        # Mostrar desglose
        print(f"\n        Doc {doc_num}/{doc_year} Item {doc_item}:")
        print(f"           +-----------------------------------------------------")
        print(f"           | CANTIDAD (peso 50%):")
        print(f"           |   Factura: {det.get('cantidad_factura', 'N/A')} | MIGO: {det.get('cantidad_entrada', 'N/A')}")
        print(f"           |   Estado: {score_result['estado_cantidad']} -> Score: {score_result['score_cantidad']:.1f}")
        print(f"           +-----------------------------------------------------")
        print(f"           | MATERIAL (peso 30%):")
        print(f"           |   MIGO: {det.get('material_entrada', 'N/A')} | OC: {det.get('material_oc', 'N/A')}")
        print(f"           |   -> Score: {score_result['score_material']:.1f}")
        print(f"           +-----------------------------------------------------")
        print(f"           | FECHA (peso 20%):")
        print(f"           |   Fecha MIGO: {det.get('fecha_entrada', 'N/A')}")
        print(f"           |   -> Score: {score_result['score_fecha']:.1f}")
        print(f"           +-----------------------------------------------------")
        print(f"           | SCORE TOTAL: {score_result['score']:.1f}/100 (minimo: {MIGO_CONFIG['score_minimo']})")
        print(f"           +-----------------------------------------------------")

        if score_result["score"] >= MIGO_CONFIG["score_minimo"] and score_result["cantidad_ok"]:
            candidatos.append({
                "MaterialDocument": doc_num,
                "MaterialDocumentYear": doc_year,
                "MaterialDocumentItem": doc_item,
                "match_score": score_result["score"],
                "cantidad_entrada": det.get("cantidad_entrada", 0),
                "estado_cantidad": score_result["estado_cantidad"],
                "score_detail": score_result,
                "entrada_data": entrada
            })
            print(f"           [OK] CANDIDATO VALIDO")
        else:
            if not score_result["cantidad_ok"]:
                print(f"           [X] NO CALIFICA: Cantidad insuficiente")
            else:
                print(f"           [X] NO CALIFICA: Score {score_result['score']:.1f} < {MIGO_CONFIG['score_minimo']}")

    # Ordenar por score y cantidad (preferir mayor cantidad disponible)
    candidatos.sort(key=lambda x: (x["match_score"], x["cantidad_entrada"]), reverse=True)

    print(f"\n     {'='*60}")
    print(f"     RESUMEN NIVEL 2 MIGO:")
    print(f"        Candidatos validos: {len(candidatos)}")
    if candidatos:
        for i, c in enumerate(candidatos[:3], 1):
            print(f"        {i}. Doc {c['MaterialDocument']}/{c['MaterialDocumentYear']}: "
                  f"Score={c['match_score']:.1f}, Cant={c['cantidad_entrada']}")
    print(f"     {'='*60}")

    return candidatos


# ============================================
# FUNCIÓN PRINCIPAL
# ============================================

def verificar_entradas_material(
    factura_datos: dict,
    oc_info: dict
) -> dict:
    """
    Verifica las entradas de material (MIGO) para una OC.

    OBLIGATORIA: Si no hay MIGO valido, no se puede facturar.

    Args:
        factura_datos: Datos de la factura
        oc_info: Información de la OC seleccionada (dict con PurchaseOrder, PurchaseOrderItem, etc.)

    Returns:
        dict con estructura:
        {
            "status": "success" | "no_match" | "error",
            "reference_document": {
                "ReferenceDocument": str,
                "ReferenceDocumentFiscalYear": str,
                "ReferenceDocumentItem": str
            },
            "match_score": float,
            "cantidad_disponible": float,
            "cantidad_factura": float,
            "error": str (si aplica)
        }
    """
    purchase_order = oc_info.get("PurchaseOrder", "")
    purchase_order_item = oc_info.get("PurchaseOrderItem", "")

    print("\n" + "=" * 70)
    print("VERIFICACION DE ENTRADA DE MATERIAL (MIGO)")
    print("=" * 70)
    print(f"  OC: {purchase_order}")
    print(f"  Item OC: {purchase_order_item}")
    print(f"  Material OC: {oc_info.get('Material', 'N/A')}")

    if not purchase_order:
        return {"status": "error", "error": "No se proporciono numero de OC"}

    try:
        # Obtener entradas de material desde SAP API
        resultado_api = fetch_entradas_material(purchase_order, purchase_order_item)

        if resultado_api["status"] != "success":
            return {"status": "error", "error": resultado_api.get("error", "Error al obtener entradas de material")}

        entradas = resultado_api["data"]
        print(f"\n  Entradas encontradas: {len(entradas)}")

        if not entradas:
            return {
                "status": "no_match",
                "error": f"No hay entradas de material (MIGO) para la OC {purchase_order}. "
                         "No se puede facturar un producto que no ha llegado a almacen."
            }

        # Filtrar solo por GoodsMovementType ya que la API no tiene ese filtro
        entradas_tipo_101 = [
            e for e in entradas
            if e.get("GoodsMovementType") == MIGO_CONFIG["goods_movement_type"]
            and not e.get("GoodsMovementIsCancelled", False)
        ]

        if not entradas_tipo_101:
            return {
                "status": "no_match",
                "error": f"No hay entradas de material con tipo 101 (entrada mercancia) para la OC {purchase_order}"
            }

        # NIVEL 1: Filtrar entradas
        entradas_filtradas = filtrar_entradas_material(entradas_tipo_101, factura_datos, oc_info)

        if not entradas_filtradas:
            return {
                "status": "no_match",
                "error": "Ninguna entrada de material paso los filtros (tipo movimiento/fecha/item)"
            }

        # NIVEL 2: Scoring
        candidatos = evaluar_migos_nivel2(entradas_filtradas, factura_datos, oc_info)

        if not candidatos:
            # Calcular cantidad total disponible para mensaje de error
            cantidad_total = sum(float(e.get("QuantityInEntryUnit", 0) or 0) for e in entradas_filtradas)
            items_factura = factura_datos.get("Items", [])
            cantidad_factura = float(items_factura[0].get("Quantity", 0) or 0) if items_factura else 0

            return {
                "status": "no_match",
                "error": f"Cantidad insuficiente en MIGO. "
                         f"Factura requiere {cantidad_factura}, disponible en almacen: {cantidad_total}",
                "cantidad_disponible": cantidad_total,
                "cantidad_factura": cantidad_factura
            }

        # Seleccionar el mejor candidato
        ganador = candidatos[0]

        print(f"\n  MIGO SELECCIONADO:")
        print(f"     Documento: {ganador['MaterialDocument']}/{ganador['MaterialDocumentYear']}")
        print(f"     Item: {ganador['MaterialDocumentItem']}")
        print(f"     Score: {ganador['match_score']:.1f}/100")
        print(f"     Cantidad disponible: {ganador['cantidad_entrada']}")

        items_factura = factura_datos.get("Items", [])
        cantidad_factura = float(items_factura[0].get("Quantity", 0) or 0) if items_factura else 0

        return {
            "status": "success",
            "reference_document": {
                "ReferenceDocument": ganador["MaterialDocument"],
                "ReferenceDocumentFiscalYear": ganador["MaterialDocumentYear"],
                "ReferenceDocumentItem": ganador["MaterialDocumentItem"]
            },
            "match_score": ganador["match_score"],
            "cantidad_disponible": ganador["cantidad_entrada"],
            "cantidad_factura": cantidad_factura,
            "estado_cantidad": ganador["estado_cantidad"]
        }

    except Exception as e:
        print(f"  [X] Excepcion: {e}")
        logger.error(f"Error en verificar_entradas_material: {e}")
        return {"status": "error", "error": str(e)}

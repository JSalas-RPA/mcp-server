# services/matchers/migo_matcher.py
# ============================================
# Matching de Entradas de Material (MIGO)
# ============================================
# Lógica de verificación de entradas de material en dos niveles:
# - Nivel 1: Filtro por API (tipo movimiento, OC, item, material)
# - Nivel 2: Match exacto por MaterialDocumentHeaderText (número de factura)
# ============================================

import logging
from datetime import datetime as dt

from tools_sap_services.sap_api import fetch_entradas_material, fetch_header_material

logger = logging.getLogger(__name__)


# ============================================
# CONFIGURACIÓN
# ============================================

MIGO_CONFIG = {
    "goods_movement_type": "101",  # Entrada de mercancía
}


# ============================================
# NIVEL 2: VERIFICACIÓN POR NÚMERO DE FACTURA
# ============================================
# Usa MaterialDocumentHeaderText para match exacto con número de factura

def normalizar_numero_factura(numero: str) -> str:
    """
    Normaliza un número de factura para comparación.
    Elimina guiones, espacios, underscores y convierte a mayúsculas.
    """
    if not numero:
        return ""
    # Eliminar caracteres especiales comunes y normalizar
    return numero.replace("-", "").replace("_", "").replace(" ", "").replace("/", "").upper().strip()


def verificar_match_header_text(entrada: dict, header: dict, factura_datos: dict) -> dict:
    """
    Verifica si el MaterialDocumentHeaderText coincide con el número de factura.

    El campo MaterialDocumentHeaderText contiene el número de factura que el
    registrador de MIGO ingresó, permitiendo un match exacto.

    Args:
        entrada: Datos del item de entrada de material
        header: Datos del header obtenidos de to_MaterialDocumentHeader
        factura_datos: Datos de la factura del OCR

    Returns:
        dict con:
        - match_exacto: bool
        - header_text: str (valor del campo)
        - numero_factura: str (número de factura de OCR)
        - razon: str (explicación del resultado)
    """
    header_text = header.get("MaterialDocumentHeaderText", "") if header else ""

    # Obtener número de factura del OCR
    numero_factura = factura_datos.get("SupplierInvoiceIDByInvcgParty", "")

    result = {
        "match_exacto": False,
        "header_text": header_text,
        "numero_factura": numero_factura,
        "razon": ""
    }

    if not header_text:
        result["razon"] = "Sin MaterialDocumentHeaderText en MIGO"
        return result

    if not numero_factura:
        result["razon"] = "Sin numero de factura en OCR"
        return result

    # Normalizar ambos valores para comparación
    header_normalizado = normalizar_numero_factura(header_text)
    factura_normalizada = normalizar_numero_factura(numero_factura)

    # Verificar match exacto
    if header_normalizado == factura_normalizada:
        result["match_exacto"] = True
        result["razon"] = "Match exacto de numero de factura"
    # Verificar si uno contiene al otro (por si hay prefijos/sufijos)
    elif header_normalizado in factura_normalizada or factura_normalizada in header_normalizado:
        result["match_exacto"] = True
        result["razon"] = "Match parcial (uno contiene al otro)"
    else:
        result["razon"] = f"No coincide: MIGO='{header_text}' vs Factura='{numero_factura}'"

    return result


def evaluar_migos_nivel2(entradas: list, factura_datos: dict, oc_info: dict) -> list:
    """
    NIVEL 2: Verificación por MaterialDocumentHeaderText.

    Para cada entrada:
    1. Obtiene el header usando to_MaterialDocumentHeader
    2. Compara MaterialDocumentHeaderText con el número de factura
    3. Si hay match exacto, la entrada es válida

    Args:
        entradas: Lista de entradas de material de la API
        factura_datos: Datos de la factura del OCR
        oc_info: Información de la OC seleccionada

    Returns:
        Lista de candidatos con match exacto
    """
    print(f"\n     NIVEL 2: Verificacion por Numero de Factura (MaterialDocumentHeaderText)")

    numero_factura = factura_datos.get("SupplierInvoiceIDByInvcgParty", "")
    print(f"        Numero de factura a buscar: '{numero_factura}'")

    candidatos = []

    for entrada in entradas:
        doc_num = entrada.get("MaterialDocument", "")
        doc_year = entrada.get("MaterialDocumentYear", "")
        doc_item = entrada.get("MaterialDocumentItem", "")
        cantidad_entrada = float(entrada.get("QuantityInEntryUnit", 0) or 0)
        material = entrada.get("Material", "")

        # Obtener el header para tener MaterialDocumentHeaderText
        print(f"\n        Consultando header de Doc {doc_num}/{doc_year}...")
        header = fetch_header_material(doc_num, doc_year)

        if not header:
            print(f"           [X] No se pudo obtener header")
            continue

        # Verificar match con header text
        match_result = verificar_match_header_text(entrada, header, factura_datos)

        # Mostrar resultado
        print(f"\n        Doc {doc_num}/{doc_year} Item {doc_item}:")
        print(f"           +-----------------------------------------------------")
        print(f"           | MaterialDocumentHeaderText: '{match_result['header_text']}'")
        print(f"           | Numero Factura OCR: '{match_result['numero_factura']}'")
        print(f"           | Resultado: {match_result['razon']}")
        print(f"           | Cantidad en MIGO: {cantidad_entrada}")
        print(f"           | Material: {material}")
        print(f"           +-----------------------------------------------------")

        if match_result["match_exacto"]:
            # Determinar estado de cantidad
            items_factura = factura_datos.get("Items", [])
            cantidad_factura = float(items_factura[0].get("Quantity", 0) or 0) if items_factura else 0

            if cantidad_entrada >= cantidad_factura:
                estado_cantidad = "OK" if cantidad_entrada == cantidad_factura else "DISPONIBLE"
                cantidad_ok = True
            else:
                estado_cantidad = "INSUFICIENTE"
                cantidad_ok = False

            candidatos.append({
                "MaterialDocument": doc_num,
                "MaterialDocumentYear": doc_year,
                "MaterialDocumentItem": doc_item,
                "match_score": 100.0,  # Match exacto = score perfecto
                "match_type": "EXACT_HEADER_TEXT",
                "header_text": match_result["header_text"],
                "cantidad_entrada": cantidad_entrada,
                "estado_cantidad": estado_cantidad,
                "cantidad_ok": cantidad_ok,
                "entrada_data": entrada,
                "header_data": header
            })
            print(f"           [OK] MATCH EXACTO - Cantidad: {estado_cantidad}")
        else:
            print(f"           [X] NO COINCIDE")

    # Ordenar por cantidad disponible (todos tienen score 100 si son match exacto)
    candidatos.sort(key=lambda x: x["cantidad_entrada"], reverse=True)

    print(f"\n     {'='*60}")
    print(f"     RESUMEN NIVEL 2 MIGO:")
    print(f"        Matches exactos encontrados: {len(candidatos)}")
    if candidatos:
        for i, c in enumerate(candidatos[:3], 1):
            print(f"        {i}. Doc {c['MaterialDocument']}/{c['MaterialDocumentYear']}: "
                  f"HeaderText='{c['header_text']}', Cant={c['cantidad_entrada']}")
    else:
        print(f"        No se encontro MIGO con el numero de factura '{numero_factura}'")
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

    OBLIGATORIA: Si no hay MIGO válido, no se puede facturar.

    Proceso:
    1. Nivel 1 (API): Filtra por OC, item, tipo movimiento 101
    2. Nivel 2: Busca match exacto de MaterialDocumentHeaderText con número de factura

    Args:
        factura_datos: Datos de la factura
        oc_info: Información de la OC seleccionada

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
            "match_type": str,
            "cantidad_disponible": float,
            "cantidad_factura": float,
            "error": str (si aplica)
        }
    """
    purchase_order = oc_info.get("PurchaseOrder", "")
    purchase_order_item = oc_info.get("PurchaseOrderItem", "")
    material = oc_info.get("Material", "")
    movement_type = MIGO_CONFIG["goods_movement_type"]

    # Obtener cantidad de la factura
    cantidad_factura = factura_datos.get("Items", [{}])[0].get("Quantity", "") if factura_datos.get("Items") else ""
    numero_factura = factura_datos.get("SupplierInvoiceIDByInvcgParty", "")

    print("\n" + "=" * 70)
    print("VERIFICACION DE ENTRADA DE MATERIAL (MIGO)")
    print("=" * 70)
    print(f"  OC: {purchase_order}")
    print(f"  Item OC: {purchase_order_item}")
    print(f"  Material OC: {material}")
    print(f"  Numero Factura: {numero_factura}")
    print(f"  Cantidad factura: {cantidad_factura}")

    if not purchase_order:
        return {"status": "error", "error": "No se proporciono numero de OC"}

    try:
        # NIVEL 1: Obtener entradas de material filtradas por API
        print(f"\n  NIVEL 1: Consulta API SAP")
        resultado_api = fetch_entradas_material(
            purchase_order,
            purchase_order_item,
            movement_type,
            cantidad_factura,
            material
        )

        if resultado_api["status"] != "success":
            return {"status": "error", "error": resultado_api.get("error", "Error al obtener entradas de material")}

        entradas = resultado_api["data"]
        print(f"  Entradas encontradas: {len(entradas)}")

        if not entradas:
            return {
                "status": "no_match",
                "error": f"No hay entradas de material (MIGO) para la OC {purchase_order}. "
                         "No se puede facturar un producto que no ha llegado a almacen."
            }

        # NIVEL 2: Verificar por MaterialDocumentHeaderText
        candidatos = evaluar_migos_nivel2(entradas, factura_datos, oc_info)

        if not candidatos:
            # No hubo match exacto por número de factura
            return {
                "status": "no_match",
                "error": f"No se encontro MIGO con numero de factura '{numero_factura}'. "
                         f"Hay {len(entradas)} entradas de material pero ninguna tiene el numero de factura correcto.",
                "entradas_encontradas": len(entradas)
            }

        # Verificar que el candidato tenga cantidad suficiente
        candidatos_ok = [c for c in candidatos if c.get("cantidad_ok", False)]

        if not candidatos_ok:
            ganador = candidatos[0]
            return {
                "status": "no_match",
                "error": f"MIGO encontrado pero cantidad insuficiente. "
                         f"Factura requiere {cantidad_factura}, disponible: {ganador['cantidad_entrada']}",
                "cantidad_disponible": ganador["cantidad_entrada"],
                "cantidad_factura": cantidad_factura
            }

        # Seleccionar el mejor candidato
        ganador = candidatos_ok[0]

        print(f"\n  MIGO SELECCIONADO:")
        print(f"     Documento: {ganador['MaterialDocument']}/{ganador['MaterialDocumentYear']}")
        print(f"     Item: {ganador['MaterialDocumentItem']}")
        print(f"     Match: {ganador['match_type']}")
        print(f"     HeaderText: '{ganador['header_text']}'")
        print(f"     Cantidad disponible: {ganador['cantidad_entrada']}")
        print(f"     Estado: {ganador['estado_cantidad']}")

        return {
            "status": "success",
            "reference_document": {
                "ReferenceDocument": ganador["MaterialDocument"],
                "ReferenceDocumentFiscalYear": ganador["MaterialDocumentYear"],
                "ReferenceDocumentItem": ganador["MaterialDocumentItem"]
            },
            "match_score": ganador["match_score"],
            "match_type": ganador["match_type"],
            "header_text": ganador["header_text"],
            "cantidad_disponible": ganador["cantidad_entrada"],
            "cantidad_factura": cantidad_factura,
            "estado_cantidad": ganador["estado_cantidad"]
        }

    except Exception as e:
        print(f"  [X] Excepcion: {e}")
        logger.error(f"Error en verificar_entradas_material: {e}")
        return {"status": "error", "error": str(e)}

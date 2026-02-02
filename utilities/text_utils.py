# utilities/text_utils.py
# ============================================
# Funciones de utilidad para procesamiento de texto
# ============================================

import re
from difflib import SequenceMatcher


def calcular_similitud_nombres(nombre1: str, nombre2: str) -> float:
    """
    Calcula la similitud entre dos nombres usando SequenceMatcher.
    Retorna un valor entre 0 y 1.
    """
    if not nombre1 or not nombre2:
        return 0.0
    return SequenceMatcher(None, nombre1.lower(), nombre2.lower()).ratio()


def limpiar_nombre_minimo(nombre: str) -> str:
    """
    Limpieza mínima: solo espacios extra, símbolos y normalización.
    NO elimina SRL, LTDA, Laboratorios, etc.
    """
    if not nombre:
        return ""

    # Convertir a mayúsculas y quitar espacios extras
    nombre = nombre.upper().strip()

    # Remover solo símbolos innecesarios pero mantener palabras
    nombre = re.sub(r'[^\w\s\.\-]', ' ', nombre)
    nombre = re.sub(r'\s+', ' ', nombre).strip()

    return nombre


def extraer_solo_numeros(texto: str) -> str:
    """
    Extrae solo los números de un texto.
    """
    if not texto:
        return ""
    return re.sub(r'\D', '', texto)


def clean_openai_json(raw_result: str) -> str:
    """
    Limpia el texto devuelto por OpenAI para que sea JSON válido.
    Remueve bloques de código markdown (```json ... ```)
    """
    if not raw_result:
        raise ValueError("Respuesta vacía de OpenAI")

    raw_result = raw_result.strip()

    if raw_result.startswith("```json"):
        raw_result = raw_result.replace("```json", "").strip()
    elif raw_result.startswith("```"):
        raw_result = raw_result.replace("```", "").strip()

    raw_result = raw_result.rstrip("`").strip()
    return raw_result


# ============================================
# FUNCIONES DE SCORING PARA OC
# ============================================

def calcular_similitud_descripcion(desc_ocr: str, desc_sap: str) -> float:
    """
    Calcula la similitud entre descripción OCR y PurchaseOrderItemText de SAP.
    Usa fuzzy matching con normalización de texto.
    Retorna un valor entre 0 y 1.
    """
    if not desc_ocr or not desc_sap:
        return 0.0

    # Normalizar ambas descripciones
    desc_ocr_norm = limpiar_nombre_minimo(desc_ocr)
    desc_sap_norm = limpiar_nombre_minimo(desc_sap)

    # Calcular similitud base
    similitud = SequenceMatcher(None, desc_ocr_norm, desc_sap_norm).ratio()

    # Bonus: si todas las palabras de OCR están en SAP (o viceversa)
    palabras_ocr = set(desc_ocr_norm.split())
    palabras_sap = set(desc_sap_norm.split())

    if palabras_ocr and palabras_sap:
        # Palabras de OCR que están en SAP
        coincidencias = palabras_ocr.intersection(palabras_sap)
        ratio_palabras = len(coincidencias) / min(len(palabras_ocr), len(palabras_sap))

        # Promedio ponderado: 60% fuzzy, 40% palabras
        similitud = (similitud * 0.6) + (ratio_palabras * 0.4)

    return min(similitud, 1.0)


def comparar_precios_unitarios(precio_ocr: float, precio_sap: float, tolerancia: float = 0.02) -> tuple[bool, float]:
    """
    Compara precios unitarios con una tolerancia porcentual.

    Args:
        precio_ocr: Precio unitario de la factura (OCR)
        precio_sap: NetPriceAmount de SAP
        tolerancia: Tolerancia porcentual (default 2%)

    Returns:
        tuple: (coincide: bool, diferencia_porcentual: float)
    """
    if precio_sap == 0:
        return (False, 1.0) if precio_ocr != 0 else (True, 0.0)

    diferencia = abs(precio_ocr - precio_sap) / precio_sap
    coincide = diferencia <= tolerancia

    return (coincide, diferencia)


def evaluar_cantidad(cantidad_ocr: float, cantidad_sap: float) -> tuple[float, str]:
    """
    Evalúa la cantidad de la factura vs la OC.

    Returns:
        tuple: (score: float 0-1, estado: str)
        - Si cantidad_ocr <= cantidad_sap: score=1.0, estado="OK" o "PARCIAL"
        - Si cantidad_ocr > cantidad_sap: score=0.0, estado="EXCESO"
    """
    if cantidad_sap <= 0:
        return (0.0, "OC_SIN_CANTIDAD")

    if cantidad_ocr <= cantidad_sap:
        estado = "PARCIAL" if cantidad_ocr < cantidad_sap else "OK"
        return (1.0, estado)
    else:
        return (0.0, "EXCESO")


def evaluar_monto_total(monto_ocr: float, monto_sap: float) -> tuple[float, str]:
    """
    Evalúa el monto total de la factura vs el monto de la OC.

    Args:
        monto_ocr: InvoiceGrossAmount de la factura
        monto_sap: NetPriceAmount * OrderQuantity de la OC

    Returns:
        tuple: (score: float 0-1, estado: str)
    """
    if monto_sap <= 0:
        return (0.0, "OC_SIN_MONTO")

    if monto_ocr <= monto_sap:
        estado = "PARCIAL" if monto_ocr < monto_sap else "OK"
        return (1.0, estado)
    else:
        # Si excede, penalizar pero no a cero (podría haber impuestos, etc.)
        exceso = (monto_ocr - monto_sap) / monto_sap
        if exceso <= 0.15:  # Hasta 15% de exceso permitido (impuestos)
            return (0.7, "EXCESO_MENOR")
        else:
            return (0.0, "EXCESO_MAYOR")

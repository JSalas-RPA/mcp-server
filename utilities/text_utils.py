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

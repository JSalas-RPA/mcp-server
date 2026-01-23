# utilities/llm_client.py
# ============================================
# Cliente de LLM (Large Language Models)
# ============================================
# Funciones para interactuar con OpenAI y otros LLMs
# Incluye funciones de extracción y validación usando IA
# ============================================

import os
import re
import json
import logging

from openai import OpenAI

from utilities.text_utils import (
    clean_openai_json,
    extraer_solo_numeros,
    calcular_similitud_descripcion,
)
from utilities.date_utils import format_sap_date
from utilities.prompts import (
    get_invoice_text_parser_prompt,
    get_invoice_validator_prompt,
    get_description_comparison_prompt,
)

# -----------------------------
# Configuración
# -----------------------------
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

logger = logging.getLogger(__name__)

# Cliente OpenAI
openai_client = OpenAI(api_key=os.getenv("API_OPENAI_KEY"))


# ============================================
# FUNCIONES BASE DE LLM
# ============================================

def get_openai_answer(system_prompt: str, user_prompt: str) -> str:
    """
    Realiza una consulta a OpenAI y retorna la respuesta.

    Args:
        system_prompt: Prompt del sistema con instrucciones
        user_prompt: Prompt del usuario con la consulta

    Returns:
        Respuesta del modelo como string
    """
    respuesta = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
    )
    return respuesta.choices[0].message.content.strip()


def get_clean_json(text: str) -> str:
    """
    Extrae el primer objeto JSON de un texto.

    Args:
        text: Texto que contiene JSON

    Returns:
        String con el JSON extraído
    """
    match = re.search(r'(\{.*\})', text, re.DOTALL)
    if match:
        return match.group(1)
    return text


# ============================================
# FUNCIONES DE EXTRACCIÓN CON IA
# ============================================

def extraer_datos_factura_desde_texto(texto_factura: str) -> dict:
    """
    Extrae datos principales de la factura desde texto OCR usando OpenAI.
    Transforma y valida los campos extraídos.

    Args:
        texto_factura: Texto OCR de la factura

    Returns:
        dict con datos estructurados de la factura
    """
    try:
        system_prompt, user_prompt = get_invoice_text_parser_prompt(texto_factura)

        logger.info("Llamando a OpenAI para extraer datos de factura...")
        raw_result = get_openai_answer(system_prompt, user_prompt)

        raw_result = clean_openai_json(raw_result)
        datos = json.loads(raw_result)

        print("\n" + "=" * 70)
        print("DATOS EXTRAIDOS DE LA FACTURA (OpenAI):")
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
                logger.warning(f"Campo requerido '{campo}' no encontrado en datos extraidos")

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
                logger.error(f"Formato de monto invalido: {datos_transformados['InvoiceGrossAmount']} - Error: {e}")
                datos_transformados["InvoiceGrossAmount"] = 0.0

        logger.info("Datos de factura extraidos y transformados exitosamente")
        return datos_transformados

    except json.JSONDecodeError as e:
        logger.error(f"Error al parsear respuesta de OpenAI: {e}")
        raise
    except Exception as e:
        logger.error(f"Error en extraccion de datos de factura: {e}")
        raise


# ============================================
# FUNCIONES DE VALIDACIÓN CON IA
# ============================================

def validar_proveedor_con_ai(factura_datos: dict, proveedores_sap: list) -> dict | None:
    """
    Usa OpenAI para validar y encontrar el proveedor correcto
    cuando la búsqueda directa falla.

    Args:
        factura_datos: Datos de la factura
        proveedores_sap: Lista de proveedores de SAP

    Returns:
        dict con info del proveedor o None si no se encuentra
    """
    try:
        factura_datos_wrapped = {"d": factura_datos}
        system_prompt, user_prompt = get_invoice_validator_prompt(factura_datos_wrapped, proveedores_sap)
        print("  Consultando a OpenAI para validar proveedor...")
        raw_result = get_openai_answer(system_prompt, user_prompt)
        raw_result = clean_openai_json(raw_result)

        proveedor_info = json.loads(raw_result)
        print(f"  Proveedor validado por AI: {proveedor_info.get('SupplierName')}")
        logger.info(f"Proveedor validado por AI: {proveedor_info.get('SupplierName')}")
        return proveedor_info

    except Exception as e:
        logger.error(f"Error en validacion de proveedor con AI: {e}")
        return None


def comparar_descripciones_con_ia(
    descripcion_ocr: str,
    descripcion_sap: str,
    codigo_ocr: str = "",
    material_sap: str = ""
) -> tuple[float, str]:
    """
    Usa IA para comparar descripciones de productos.
    Útil cuando los nombres varían (ej: "Aspirinita" vs "Ácido Acetilsalicílico").

    Args:
        descripcion_ocr: Descripción del producto en la factura
        descripcion_sap: Descripción del producto en SAP (PurchaseOrderItemText)
        codigo_ocr: Código del producto en la factura (opcional)
        material_sap: Código del material en SAP (opcional)

    Returns:
        tuple: (score 0-1, razón de la decisión)
    """
    try:
        # Si hay match exacto de código, no necesitamos IA
        if codigo_ocr and material_sap and str(codigo_ocr) == str(material_sap):
            return (1.0, "Codigo de material coincide exactamente")

        # Si alguna descripción está vacía
        if not descripcion_ocr or not descripcion_sap:
            return (0.0, "Descripcion vacia")

        system_prompt, user_prompt = get_description_comparison_prompt(
            descripcion_ocr, descripcion_sap, codigo_ocr, material_sap
        )

        raw_result = get_openai_answer(system_prompt, user_prompt)
        raw_result = clean_openai_json(raw_result)

        result = json.loads(raw_result)

        match = result.get("match", False)
        confidence = float(result.get("confidence", 0.0))
        reason = result.get("reason", "Sin razon")

        # Si es match, usar la confianza como score
        # Si no es match, score bajo proporcional a la confianza inversa
        if match:
            score = confidence
        else:
            score = (1 - confidence) * 0.3  # Máximo 0.3 si no hay match

        return (score, reason)

    except Exception as e:
        logger.warning(f"Error en comparacion IA de descripciones: {e}")
        # Fallback a comparación básica
        score = calcular_similitud_descripcion(descripcion_ocr, descripcion_sap)
        return (score, f"Fallback fuzzy match (error IA: {str(e)[:50]})")

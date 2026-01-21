# verification/ocr_comparator.py
"""
Comparación de resultados de diferentes motores OCR.
"""

import re
import logging
from difflib import SequenceMatcher
from typing import Optional, Tuple, List
from collections import Counter

from .schemas import OCRComparison

logger = logging.getLogger(__name__)


class OCRComparator:
    """Comparador de resultados de diferentes motores OCR."""

    def __init__(self):
        self.ocr_methods = {
            "google_cloud_vision": self._get_gcv_text,
            "llamaparse": self._get_llamaparse_text,
            "pymupdf": self._get_pymupdf_text,
        }

    def _get_gcv_text(self, pdf_path: str) -> Optional[str]:
        """Extrae texto usando Google Cloud Vision."""
        try:
            from utilities.general import get_transcript_document_cloud_vision
            return get_transcript_document_cloud_vision(pdf_path)
        except Exception as e:
            logger.error(f"Error en Google Cloud Vision OCR: {e}")
            return None

    def _get_llamaparse_text(self, pdf_path: str) -> Optional[str]:
        """Extrae texto usando LlamaParse."""
        try:
            from utilities.general import get_transcript_document
            return get_transcript_document(pdf_path)
        except Exception as e:
            logger.error(f"Error en LlamaParse OCR: {e}")
            return None

    def _get_pymupdf_text(self, pdf_path: str) -> Optional[str]:
        """Extrae texto usando PyMuPDF (solo para PDFs nativos con texto)."""
        try:
            from utilities.general import extract_text_from_first_page
            text = extract_text_from_first_page(pdf_path)
            if text and not text.startswith("ERROR"):
                return text
            return None
        except Exception as e:
            logger.error(f"Error en PyMuPDF: {e}")
            return None

    def compare_ocr_results(
        self,
        pdf_path: str,
        primary_method: str = "google_cloud_vision",
        alternative_method: str = "pymupdf"
    ) -> Tuple[OCRComparison, Optional[str], Optional[str]]:
        """
        Compara resultados de dos métodos OCR.

        Args:
            pdf_path: Ruta al archivo PDF
            primary_method: Método OCR principal
            alternative_method: Método OCR alternativo

        Returns:
            Tupla con (OCRComparison, texto_principal, texto_alternativo)
        """
        logger.info(f"Comparando OCR: {primary_method} vs {alternative_method}")

        # Obtener textos
        texto_principal = None
        texto_alternativo = None

        if primary_method in self.ocr_methods:
            texto_principal = self.ocr_methods[primary_method](pdf_path)

        if alternative_method in self.ocr_methods:
            texto_alternativo = self.ocr_methods[alternative_method](pdf_path)

        # Calcular similitud y diferencias
        similitud = 0.0
        diferencias = []
        recomendacion = None

        # Solo procedemos si ambos textos existen
        if texto_principal and texto_alternativo:
            # 1. Normalizar a LISTAS de palabras
            tokens_prim = self._normalize_to_list(texto_principal)
            tokens_alt = self._normalize_to_list(texto_alternativo)
            # 2. Calcular similitud:
            sim_secuencial = self._calculate_list_similarity(tokens_prim, tokens_alt)
            sim_contenido = self._calculate_bag_of_words_similarity(tokens_prim, tokens_alt)
            # Lógica de decisión
            if sim_contenido > sim_secuencial and sim_contenido > 0.8:
                similitud = sim_contenido
                logger.info(f"Usando similitud de contenido (Bolsa de Palabras): {sim_contenido:.2%} vs Secuencial: {sim_secuencial:.2%}")
            else:
                similitud = sim_secuencial
            # 3. Encontrar diferencias (usando los textos originales para contexto)
            diferencias = self._find_key_differences(texto_principal, texto_alternativo)
            # 4. Generar recomendación
            recomendacion = self._make_recommendation(
                texto_principal, texto_alternativo, primary_method, alternative_method, similitud
            )
            
        elif texto_principal:
            recomendacion = f"Solo {primary_method} extrajo texto."
        elif texto_alternativo:
            recomendacion = f"Solo {alternative_method} extrajo texto."

        # Crear objeto de resultado
        comparison = OCRComparison(
            ejecutada=True,
            ocr_principal=primary_method,
            ocr_alternativo=alternative_method,
            similitud_texto=similitud,
            diferencias_clave=diferencias,
            recomendacion=recomendacion,
            texto_principal_preview=texto_principal[:200] if texto_principal else "",
            texto_alternativo_preview=texto_alternativo[:200] if texto_alternativo else ""
        )

        return comparison, texto_principal, texto_alternativo

    def _normalize_to_list(self, text: str) -> List[str]:
        """
        Convierte el texto en una lista limpia de palabras.
        Rompe el texto por espacios y saltos de línea, elimina vacíos.
        """
        if not text:
            return []
        
        text = text.lower()
        text = text.replace('\n', ' ').replace('\t', ' ')
        text = re.sub(r'[^\w\s.,]', '', text)
        words = text.split()

        return [w for w in words if w.strip()]

    def _calculate_list_similarity(self, list1: List[str], list2: List[str]) -> float:
        """Calcula la similitud respetando el ORDEN de las palabras."""
        if not list1 and not list2: return 1.0
        if not list1 or not list2: return 0.0
        matcher = SequenceMatcher(None, list1, list2, autojunk=False)
        return matcher.ratio()

    def _calculate_bag_of_words_similarity(self, list1: List[str], list2: List[str]) -> float:
        """
        Calcula la similitud IGNORANDO el orden (Histograma de palabras).
        Ideal para comparar PyMuPDF (stream order) vs Vision (layout order).
        """
        if not list1 and not list2: return 1.0
        if not list1 or not list2: return 0.0

        c1 = Counter(list1)
        c2 = Counter(list2)
        
        intersection = sum((c1 & c2).values())

        total_elements = sum(c1.values()) + sum(c2.values())
        
        if total_elements == 0: return 0.0
        
        return 2.0 * intersection / total_elements

    def _find_key_differences(self, text1: str, text2: str) -> List[str]:
        """Busca diferencias en valores clave específicos (NIT, Total, Fechas)."""
        diferencias = []
        # Definimos patrones regex para buscar datos clave
        patrones = [
            (r'NIT[:\s.]*(\d+)', 'NIT'),
            (r'Total[:\s$]*([\d,.]+)', 'Total'),
            (r'Fecha[:\s]*(\d{2,4}[-/]\d{2}[-/]\d{2,4})', 'Fecha'),
        ]

        for regex, label in patrones:
            val1 = re.search(regex, text1, re.IGNORECASE)
            val2 = re.search(regex, text2, re.IGNORECASE)

            v1_str = val1.group(1) if val1 else "No encontrado"
            v2_str = val2.group(1) if val2 else "No encontrado"

            # Normalización simple para comparar valores (quitar comas en números, etc)
            clean_v1 = v1_str.replace(',', '').replace('.', '')
            clean_v2 = v2_str.replace(',', '').replace('.', '')

            if clean_v1 != clean_v2:
                diferencias.append(f"{label}: '{v1_str}' vs '{v2_str}'")

        return diferencias

    def _make_recommendation(self, t1, t2, m1, m2, similarity) -> str:
        """Genera una recomendación inteligente."""
        if similarity > 0.95:
            return "Resultados casi idénticos. Usar cualquiera."
        
        if similarity > 0.8:
            return f"Alta similitud ({similarity:.2%}). Contenido verificado."

        # Si son muy diferentes, preferir el que tenga más "contenido útil" (palabras)
        len1 = len(t1.split())
        len2 = len(t2.split())
        
        if len1 > len2 * 1.5:
            return f"Usar {m1}. Parece haber extraído mucho más contenido ({len1} palabras vs {len2})."
        elif len2 > len1 * 1.5:
            return f"Usar {m2}. Parece haber extraído mucho más contenido ({len2} palabras vs {len1})."
            
        return f"Revisión manual requerida. Similitud baja ({similarity:.2%})."

    def get_combined_context(
        self,
        pdf_path: str,
        methods: list[str] = None
    ) -> dict[str, str]:
        """
        Obtiene texto de múltiples métodos para usar como contexto combinado.

        Args:
            pdf_path: Ruta al PDF
            methods: Lista de métodos a usar (default: todos los disponibles)

        Returns:
            Diccionario {método: texto}
        """
        if methods is None:
            methods = list(self.ocr_methods.keys())

        resultados = {}
        for method in methods:
            if method in self.ocr_methods:
                texto = self.ocr_methods[method](pdf_path)
                if texto:
                    resultados[method] = texto

        return resultados

    def extract_with_method(self, pdf_path: str, method: str) -> Optional[str]:
        """
        Extrae texto usando un método específico.

        Args:
            pdf_path: Ruta al PDF
            method: Nombre del método OCR

        Returns:
            Texto extraído o None si falla
        """
        if method not in self.ocr_methods:
            logger.error(f"Método OCR no soportado: {method}")
            return None

        return self.ocr_methods[method](pdf_path)

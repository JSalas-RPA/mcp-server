# verification/ocr_comparator.py
"""
Comparación de resultados de diferentes motores OCR.
"""

import re
import logging
from difflib import SequenceMatcher
from typing import Optional, Tuple

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

        if texto_principal and texto_alternativo:
            similitud = self._calculate_similarity(texto_principal, texto_alternativo)
            diferencias = self._find_key_differences(texto_principal, texto_alternativo)
            recomendacion = self._make_recommendation(
                texto_principal, texto_alternativo, primary_method, alternative_method
            )
        elif texto_principal and not texto_alternativo:
            recomendacion = f"Solo {primary_method} produjo resultado. PDF probablemente escaneado."
        elif not texto_principal and texto_alternativo:
            recomendacion = f"Solo {alternative_method} produjo resultado. Verificar configuración de {primary_method}."
        else:
            recomendacion = "Ningún método produjo resultado. Verificar calidad del PDF."

        comparison = OCRComparison(
            ejecutada=True,
            ocr_principal=primary_method,
            ocr_alternativo=alternative_method,
            similitud_texto=similitud,
            diferencias_clave=diferencias,
            recomendacion=recomendacion,
            texto_principal_preview=texto_principal[:500] if texto_principal else None,
            texto_alternativo_preview=texto_alternativo[:500] if texto_alternativo else None,
        )

        return comparison, texto_principal, texto_alternativo

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calcula similitud entre dos textos (0.0 a 1.0)."""
        # Normalizar textos
        t1 = self._normalize_text(text1)
        t2 = self._normalize_text(text2)

        return SequenceMatcher(None, t1, t2).ratio()

    def _normalize_text(self, text: str) -> str:
        """Normaliza texto para comparación."""
        # Convertir a minúsculas
        text = text.lower()
        # Remover espacios múltiples
        text = re.sub(r'\s+', ' ', text)
        # Remover caracteres especiales excepto números y letras
        text = re.sub(r'[^\w\s]', '', text)
        return text.strip()

    def _find_key_differences(self, text1: str, text2: str, max_diffs: int = 5) -> list[str]:
        """Encuentra diferencias clave entre dos textos."""
        diferencias = []

        # Buscar patrones importantes
        patrones = [
            (r'NIT[:\s]*(\d+)', 'NIT'),
            (r'Total[:\s]*([\d,\.]+)', 'Total'),
            (r'Factura[:\s#N°]*(\d+)', 'N° Factura'),
            (r'Fecha[:\s]*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})', 'Fecha'),
        ]

        for patron, nombre in patrones:
            match1 = re.search(patron, text1, re.IGNORECASE)
            match2 = re.search(patron, text2, re.IGNORECASE)

            val1 = match1.group(0) if match1 else "No encontrado"
            val2 = match2.group(0) if match2 else "No encontrado"

            if val1 != val2:
                diferencias.append(f"{nombre}: Principal='{val1}' vs Alternativo='{val2}'")

        return diferencias[:max_diffs]

    def _make_recommendation(
        self,
        text1: str,
        text2: str,
        method1: str,
        method2: str
    ) -> str:
        """Genera recomendación basada en la comparación."""
        len1 = len(text1) if text1 else 0
        len2 = len(text2) if text2 else 0

        # Verificar si PyMuPDF extrajo poco texto (PDF escaneado)
        if method2 == "pymupdf" and len2 < 100 and len1 > 500:
            return f"Usar {method1}. El PDF parece ser escaneado (PyMuPDF extrajo poco texto)."

        # Si ambos tienen contenido similar, preferir el más completo
        if len1 >= len2:
            return f"Usar {method1} (texto más completo: {len1} vs {len2} caracteres)."
        else:
            return f"Considerar {method2} (texto más completo: {len2} vs {len1} caracteres)."

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

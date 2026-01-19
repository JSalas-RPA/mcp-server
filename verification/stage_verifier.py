# verification/stage_verifier.py
"""
Verificación de resultados por etapa del flujo de facturas.
"""

import re
import logging
from typing import Any, Optional

from .schemas import (
    VerificationDetails,
    VerificationResult,
    GroundTruthEntry,
)

logger = logging.getLogger(__name__)


class StageVerifier:
    """Verificador de resultados por etapa."""

    def __init__(self, ground_truth: Optional[GroundTruthEntry] = None):
        """
        Inicializa el verificador.

        Args:
            ground_truth: Datos esperados para verificación.
                         Si es None, no se ejecuta verificación.
        """
        self.ground_truth = ground_truth

    def verify_ocr(self, texto_extraido: str) -> VerificationDetails:
        """
        Verifica el resultado del OCR.

        Args:
            texto_extraido: Texto obtenido del OCR

        Returns:
            VerificationDetails con resultado de verificación
        """
        if not self.ground_truth:
            return VerificationDetails(
                ejecutada=False,
                resultado=VerificationResult.NOT_EXECUTED,
                mensaje="Sin ground truth disponible"
            )

        expected = self.ground_truth.ocr_esperado
        detalles = {}
        errores = []

        # Verificar longitud mínima
        char_count = len(texto_extraido) if texto_extraido else 0
        detalles["caracteres_extraidos"] = char_count
        if char_count < expected.texto_minimo_caracteres:
            errores.append(f"Texto muy corto: {char_count} < {expected.texto_minimo_caracteres}")

        # Verificar keywords requeridos
        keywords_encontrados = []
        keywords_faltantes = []
        texto_upper = texto_extraido.upper() if texto_extraido else ""

        for keyword in expected.keywords_requeridos:
            if keyword.upper() in texto_upper:
                keywords_encontrados.append(keyword)
            else:
                keywords_faltantes.append(keyword)

        detalles["keywords_encontrados"] = keywords_encontrados
        detalles["keywords_faltantes"] = keywords_faltantes

        if keywords_faltantes:
            errores.append(f"Keywords faltantes: {keywords_faltantes}")

        # Verificar patrones
        if expected.patron_nit:
            patron_nit_encontrado = bool(re.search(expected.patron_nit, texto_extraido or ""))
            detalles["patron_nit_encontrado"] = patron_nit_encontrado
            if not patron_nit_encontrado:
                errores.append("Patrón NIT no encontrado")

        if expected.patron_monto:
            patron_monto_encontrado = bool(re.search(expected.patron_monto, texto_extraido or ""))
            detalles["patron_monto_encontrado"] = patron_monto_encontrado
            if not patron_monto_encontrado:
                errores.append("Patrón monto no encontrado")

        # Determinar resultado
        if not errores:
            resultado = VerificationResult.PASS
            mensaje = "OCR verificado correctamente"
        elif len(errores) == 1 and "Keywords faltantes" in errores[0]:
            resultado = VerificationResult.WARNING
            mensaje = f"OCR parcialmente verificado: {errores[0]}"
        else:
            resultado = VerificationResult.FAIL
            mensaje = f"OCR falló verificación: {'; '.join(errores)}"

        return VerificationDetails(
            ejecutada=True,
            resultado=resultado,
            detalles=detalles,
            mensaje=mensaje
        )

    def verify_parsing(self, datos_parseados: dict) -> VerificationDetails:
        """
        Verifica el resultado del parsing.

        Args:
            datos_parseados: Datos estructurados extraídos

        Returns:
            VerificationDetails con resultado de verificación
        """
        if not self.ground_truth:
            return VerificationDetails(
                ejecutada=False,
                resultado=VerificationResult.NOT_EXECUTED,
                mensaje="Sin ground truth disponible"
            )

        expected = self.ground_truth.parsing_esperado
        detalles = {"valores_coinciden": {}}
        errores = []

        # Verificar campos requeridos
        campos_encontrados = []
        campos_faltantes = []

        for campo in expected.campos_requeridos:
            if campo in datos_parseados and datos_parseados[campo] is not None:
                campos_encontrados.append(campo)
            else:
                campos_faltantes.append(campo)

        detalles["campos_encontrados"] = campos_encontrados
        detalles["campos_faltantes"] = campos_faltantes

        if campos_faltantes:
            errores.append(f"Campos requeridos faltantes: {campos_faltantes}")

        # Verificar valores esperados
        for campo, valor_esperado in expected.valores_esperados.items():
            valor_obtenido = datos_parseados.get(campo)

            match = self._compare_values(
                valor_esperado,
                valor_obtenido,
                expected.tolerancia_numerica
            )

            detalles["valores_coinciden"][campo] = {
                "esperado": valor_esperado,
                "obtenido": valor_obtenido,
                "match": match
            }

            if not match:
                errores.append(f"{campo}: esperado '{valor_esperado}', obtenido '{valor_obtenido}'")

        # Determinar resultado
        if not errores:
            resultado = VerificationResult.PASS
            mensaje = "Parsing verificado correctamente"
        elif len(errores) <= 2:
            resultado = VerificationResult.WARNING
            mensaje = f"Parsing parcialmente verificado: {len(errores)} discrepancias"
        else:
            resultado = VerificationResult.FAIL
            mensaje = f"Parsing falló verificación: {len(errores)} errores"

        return VerificationDetails(
            ejecutada=True,
            resultado=resultado,
            detalles=detalles,
            mensaje=mensaje
        )

    def verify_proveedor(self, proveedor_info: dict) -> VerificationDetails:
        """
        Verifica el resultado de la validación de proveedor.

        Args:
            proveedor_info: Información del proveedor encontrado

        Returns:
            VerificationDetails con resultado de verificación
        """
        if not self.ground_truth:
            return VerificationDetails(
                ejecutada=False,
                resultado=VerificationResult.NOT_EXECUTED,
                mensaje="Sin ground truth disponible"
            )

        expected = self.ground_truth.proveedor_esperado
        detalles = {}
        errores = []

        # Verificar código de proveedor
        if expected.Supplier:
            supplier_obtenido = proveedor_info.get("Supplier", "")
            detalles["supplier_esperado"] = expected.Supplier
            detalles["supplier_obtenido"] = supplier_obtenido
            detalles["supplier_match"] = supplier_obtenido == expected.Supplier

            if supplier_obtenido != expected.Supplier:
                errores.append(f"Supplier: esperado '{expected.Supplier}', obtenido '{supplier_obtenido}'")

        # Verificar nombre de proveedor
        if expected.SupplierName:
            nombre_obtenido = proveedor_info.get("SupplierName", "")
            similitud = proveedor_info.get("Similitud", 0)

            detalles["nombre_esperado"] = expected.SupplierName
            detalles["nombre_obtenido"] = nombre_obtenido
            detalles["similitud"] = similitud
            detalles["similitud_minima"] = expected.similitud_minima

            if similitud < expected.similitud_minima:
                errores.append(f"Similitud insuficiente: {similitud:.2f} < {expected.similitud_minima}")

        # Determinar resultado
        if not errores:
            resultado = VerificationResult.PASS
            mensaje = "Proveedor verificado correctamente"
        else:
            resultado = VerificationResult.FAIL
            mensaje = f"Proveedor falló verificación: {'; '.join(errores)}"

        return VerificationDetails(
            ejecutada=True,
            resultado=resultado,
            detalles=detalles,
            mensaje=mensaje
        )

    def verify_ordenes_compra(self, oc_items: list) -> VerificationDetails:
        """
        Verifica el resultado de la búsqueda de OC.

        Args:
            oc_items: Lista de items de OC encontrados

        Returns:
            VerificationDetails con resultado de verificación
        """
        if not self.ground_truth:
            return VerificationDetails(
                ejecutada=False,
                resultado=VerificationResult.NOT_EXECUTED,
                mensaje="Sin ground truth disponible"
            )

        expected = self.ground_truth.oc_esperado
        detalles = {}
        errores = []

        # Verificar si se encontró OC
        oc_encontradas = len(oc_items) > 0
        detalles["debe_encontrar_oc"] = expected.debe_encontrar_oc
        detalles["oc_encontradas"] = len(oc_items)

        if expected.debe_encontrar_oc and not oc_encontradas:
            errores.append("No se encontraron OCs (se esperaba al menos una)")
        elif not expected.debe_encontrar_oc and oc_encontradas:
            errores.append("Se encontraron OCs cuando no se esperaban")

        # Verificar OC específica si se proporcionó
        if expected.PurchaseOrder and oc_items:
            oc_encontrada = any(
                item.get("PurchaseOrder") == expected.PurchaseOrder
                for item in oc_items
            )
            detalles["purchase_order_esperado"] = expected.PurchaseOrder
            detalles["purchase_order_encontrado"] = oc_encontrada

            if not oc_encontrada:
                errores.append(f"OC esperada '{expected.PurchaseOrder}' no encontrada")

        # Verificar campos requeridos en OC
        if oc_items:
            primera_oc = oc_items[0]
            campos_faltantes = [
                campo for campo in expected.campos_requeridos
                if campo not in primera_oc or primera_oc[campo] is None
            ]

            detalles["campos_requeridos"] = expected.campos_requeridos
            detalles["campos_faltantes_oc"] = campos_faltantes

            if campos_faltantes:
                errores.append(f"Campos faltantes en OC: {campos_faltantes}")

        # Determinar resultado
        if not errores:
            resultado = VerificationResult.PASS
            mensaje = "OC verificada correctamente"
        else:
            resultado = VerificationResult.FAIL
            mensaje = f"OC falló verificación: {'; '.join(errores)}"

        return VerificationDetails(
            ejecutada=True,
            resultado=resultado,
            detalles=detalles,
            mensaje=mensaje
        )

    def verify_json_sap(self, factura_json: dict) -> VerificationDetails:
        """
        Verifica el JSON construido para SAP.

        Args:
            factura_json: JSON listo para enviar a SAP

        Returns:
            VerificationDetails con resultado de verificación
        """
        if not self.ground_truth:
            return VerificationDetails(
                ejecutada=False,
                resultado=VerificationResult.NOT_EXECUTED,
                mensaje="Sin ground truth disponible"
            )

        expected = self.ground_truth.json_sap_esperado
        detalles = {"valores_coinciden": {}}
        errores = []

        # Verificar campos requeridos
        campos_faltantes = [
            campo for campo in expected.campos_requeridos
            if campo not in factura_json or factura_json[campo] is None
        ]

        detalles["campos_requeridos"] = expected.campos_requeridos
        detalles["campos_faltantes"] = campos_faltantes

        if campos_faltantes:
            errores.append(f"Campos requeridos faltantes: {campos_faltantes}")

        # Verificar valores esperados
        for campo, valor_esperado in expected.valores_esperados.items():
            valor_obtenido = factura_json.get(campo)
            match = str(valor_esperado) == str(valor_obtenido)

            detalles["valores_coinciden"][campo] = {
                "esperado": valor_esperado,
                "obtenido": valor_obtenido,
                "match": match
            }

            if not match:
                errores.append(f"{campo}: esperado '{valor_esperado}', obtenido '{valor_obtenido}'")

        # Verificar estructura de items
        items = factura_json.get("to_SuplrInvcItemPurOrdRef", {}).get("results", [])
        detalles["items_count"] = len(items)

        if not items:
            errores.append("JSON no tiene items de OC")

        # Determinar resultado
        if not errores:
            resultado = VerificationResult.PASS
            mensaje = "JSON SAP verificado correctamente"
        elif len(errores) == 1:
            resultado = VerificationResult.WARNING
            mensaje = f"JSON SAP parcialmente verificado: {errores[0]}"
        else:
            resultado = VerificationResult.FAIL
            mensaje = f"JSON SAP falló verificación: {len(errores)} errores"

        return VerificationDetails(
            ejecutada=True,
            resultado=resultado,
            detalles=detalles,
            mensaje=mensaje
        )

    def _compare_values(
        self,
        expected: Any,
        obtained: Any,
        tolerance: float = 0.01
    ) -> bool:
        """Compara dos valores con tolerancia para numéricos."""
        if expected is None:
            return True  # Si no hay valor esperado, cualquier cosa es válida

        if obtained is None:
            return False

        # Comparación numérica con tolerancia
        try:
            exp_num = float(expected)
            obt_num = float(obtained)
            if exp_num == 0:
                return obt_num == 0
            return abs(exp_num - obt_num) / abs(exp_num) <= tolerance
        except (ValueError, TypeError):
            pass

        # Comparación de strings (case insensitive, trimmed)
        return str(expected).strip().upper() == str(obtained).strip().upper()

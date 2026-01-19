# verification/ground_truth.py
"""
Manejo de datos de referencia (ground truth) para verificación.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from .schemas import (
    GroundTruthEntry,
    OCRExpected,
    ParsingExpected,
    ProveedorExpected,
    OCExpected,
    JSONSAPExpected,
)

logger = logging.getLogger(__name__)

# Ruta por defecto para ground truth
DEFAULT_GROUND_TRUTH_DIR = Path(__file__).parent.parent / "data" / "ground_truth"


class GroundTruthManager:
    """Gestor de datos de referencia para verificación de facturas."""

    def __init__(self, ground_truth_path: Optional[str] = None):
        """
        Inicializa el gestor de ground truth.

        Args:
            ground_truth_path: Ruta al archivo JSON con datos de referencia.
                              Si no se especifica, usa el archivo por defecto.
        """
        if ground_truth_path:
            self.ground_truth_path = Path(ground_truth_path)
        else:
            self.ground_truth_path = DEFAULT_GROUND_TRUTH_DIR / "facturas_test.json"

        self._data: Optional[dict] = None
        self._load_ground_truth()

    def _load_ground_truth(self) -> None:
        """Carga el archivo de ground truth."""
        try:
            if self.ground_truth_path.exists():
                with open(self.ground_truth_path, 'r', encoding='utf-8') as f:
                    self._data = json.load(f)
                logger.info(f"Ground truth cargado desde: {self.ground_truth_path}")
            else:
                logger.warning(f"Archivo de ground truth no encontrado: {self.ground_truth_path}")
                self._data = {"_metadata": {}, "facturas": {}}
        except Exception as e:
            logger.error(f"Error al cargar ground truth: {e}")
            self._data = {"_metadata": {}, "facturas": {}}

    def get_entry_for_file(self, filename: str) -> Optional[GroundTruthEntry]:
        """
        Obtiene la entrada de ground truth para un archivo.

        Args:
            filename: Nombre del archivo PDF (ej: "factura_viva.pdf")

        Returns:
            GroundTruthEntry si existe, None si no.
        """
        # Extraer solo el nombre del archivo si viene con ruta
        filename = Path(filename).name

        if not self._data or filename not in self._data.get("facturas", {}):
            logger.warning(f"No hay ground truth para: {filename}")
            return None

        entry_data = self._data["facturas"][filename]

        try:
            return GroundTruthEntry(
                ocr_esperado=self._parse_ocr_expected(entry_data.get("ocr_esperado", {})),
                parsing_esperado=self._parse_parsing_expected(entry_data.get("parsing_esperado", {})),
                proveedor_esperado=self._parse_proveedor_expected(entry_data.get("proveedor_esperado", {})),
                oc_esperado=self._parse_oc_expected(entry_data.get("oc_esperado", {})),
                json_sap_esperado=self._parse_json_sap_expected(entry_data.get("json_sap_esperado", {})),
            )
        except Exception as e:
            logger.error(f"Error al parsear ground truth para {filename}: {e}")
            return None

    def _parse_ocr_expected(self, data: dict) -> OCRExpected:
        return OCRExpected(
            keywords_requeridos=data.get("keywords_requeridos", []),
            texto_minimo_caracteres=data.get("texto_minimo_caracteres", 100),
            patron_nit=data.get("patron_nit"),
            patron_monto=data.get("patron_monto"),
        )

    def _parse_parsing_expected(self, data: dict) -> ParsingExpected:
        # Crear copia para no modificar el original
        data_copy = data.copy()
        campos_requeridos = data_copy.pop("campos_requeridos", [])
        tolerancia = data_copy.pop("tolerancia_numerica", 0.01)
        return ParsingExpected(
            campos_requeridos=campos_requeridos,
            valores_esperados=data_copy,
            tolerancia_numerica=tolerancia,
        )

    def _parse_proveedor_expected(self, data: dict) -> ProveedorExpected:
        return ProveedorExpected(
            Supplier=data.get("Supplier"),
            SupplierName=data.get("SupplierName"),
            similitud_minima=data.get("similitud_minima", 0.8),
        )

    def _parse_oc_expected(self, data: dict) -> OCExpected:
        return OCExpected(
            debe_encontrar_oc=data.get("debe_encontrar_oc", True),
            PurchaseOrder=data.get("PurchaseOrder"),
            campos_requeridos=data.get("campos_requeridos", ["PurchaseOrder", "PurchaseOrderItem"]),
        )

    def _parse_json_sap_expected(self, data: dict) -> JSONSAPExpected:
        # Crear copia para no modificar el original
        data_copy = data.copy()
        campos_requeridos = data_copy.pop("campos_requeridos", [])
        return JSONSAPExpected(
            campos_requeridos=campos_requeridos,
            valores_esperados=data_copy,
        )

    def list_available_files(self) -> list[str]:
        """Lista todos los archivos con ground truth disponible."""
        if not self._data:
            return []
        return list(self._data.get("facturas", {}).keys())

    def add_entry(self, filename: str, entry: dict) -> bool:
        """
        Agrega o actualiza una entrada de ground truth.

        Args:
            filename: Nombre del archivo PDF
            entry: Diccionario con los datos esperados

        Returns:
            True si se guardó correctamente
        """
        try:
            if not self._data:
                self._data = {"_metadata": {}, "facturas": {}}

            self._data["facturas"][filename] = entry

            # Guardar al archivo
            self.ground_truth_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.ground_truth_path, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)

            logger.info(f"Ground truth actualizado para: {filename}")
            return True
        except Exception as e:
            logger.error(f"Error al guardar ground truth: {e}")
            return False

    def reload(self) -> None:
        """Recarga el archivo de ground truth."""
        self._load_ground_truth()

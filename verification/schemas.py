# verification/schemas.py
"""
Definiciones de tipos y esquemas para el sistema de verificación.
"""

from dataclasses import dataclass, field
from typing import Optional, Any
from datetime import datetime
from enum import Enum


class StageStatus(Enum):
    """Estados posibles de una etapa."""
    SUCCESS = "success"
    ERROR = "error"
    SKIPPED = "skipped"


class VerificationResult(Enum):
    """Resultados de verificación."""
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    NOT_EXECUTED = "not_executed"


class ExecutionResult(Enum):
    """Resultado global de ejecución."""
    SUCCESS = "success"
    PARTIAL = "partial"
    ERROR = "error"


@dataclass
class OCRExpected:
    """Datos esperados para verificación de OCR."""
    keywords_requeridos: list[str]
    texto_minimo_caracteres: int = 100
    patron_nit: Optional[str] = None
    patron_monto: Optional[str] = None


@dataclass
class ParsingExpected:
    """Datos esperados para verificación de parsing."""
    campos_requeridos: list[str]
    valores_esperados: dict[str, Any] = field(default_factory=dict)
    tolerancia_numerica: float = 0.01


@dataclass
class ProveedorExpected:
    """Datos esperados para verificación de proveedor."""
    Supplier: Optional[str] = None
    SupplierName: Optional[str] = None
    similitud_minima: float = 0.8


@dataclass
class OCExpected:
    """Datos esperados para verificación de OC."""
    debe_encontrar_oc: bool = True
    PurchaseOrder: Optional[str] = None
    campos_requeridos: list[str] = field(default_factory=lambda: ["PurchaseOrder", "PurchaseOrderItem"])


@dataclass
class JSONSAPExpected:
    """Datos esperados para verificación de JSON SAP."""
    campos_requeridos: list[str]
    valores_esperados: dict[str, Any] = field(default_factory=dict)


@dataclass
class GroundTruthEntry:
    """Entrada completa de ground truth para una factura."""
    ocr_esperado: OCRExpected
    parsing_esperado: ParsingExpected
    proveedor_esperado: ProveedorExpected
    oc_esperado: OCExpected
    json_sap_esperado: JSONSAPExpected


@dataclass
class VerificationDetails:
    """Detalles de una verificación individual."""
    ejecutada: bool
    resultado: VerificationResult
    detalles: dict[str, Any] = field(default_factory=dict)
    mensaje: Optional[str] = None


@dataclass
class OCRComparison:
    """Resultado de comparación de OCR."""
    ejecutada: bool
    ocr_principal: str
    ocr_alternativo: str
    similitud_texto: float
    diferencias_clave: list[str] = field(default_factory=list)
    recomendacion: Optional[str] = None
    texto_principal_preview: Optional[str] = None
    texto_alternativo_preview: Optional[str] = None


@dataclass
class StageResult:
    """Resultado de una etapa del flujo."""
    etapa: int
    nombre: str
    descripcion: str
    timestamp_inicio: datetime
    timestamp_fin: Optional[datetime] = None
    duracion_ms: Optional[int] = None
    status: StageStatus = StageStatus.SUCCESS
    verificacion: Optional[VerificationDetails] = None
    comparacion_ocr: Optional[OCRComparison] = None
    data: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class ExecutionLog:
    """Log completo de una ejecución."""
    execution_id: str
    timestamp_inicio: datetime
    archivo_entrada: str
    ground_truth_usado: Optional[str] = None
    modo: str = "verificacion"
    timestamp_fin: Optional[datetime] = None
    duracion_segundos: Optional[float] = None
    resultado_global: ExecutionResult = ExecutionResult.SUCCESS
    resumen: dict[str, Any] = field(default_factory=dict)
    etapas: list[StageResult] = field(default_factory=list)
    contexto_adicional: dict[str, Any] = field(default_factory=dict)

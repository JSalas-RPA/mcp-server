# verification/__init__.py
"""
Sistema de verificación y logging para flujo de facturas.
"""

from .schemas import (
    StageStatus,
    VerificationResult,
    ExecutionResult,
    OCRExpected,
    ParsingExpected,
    ProveedorExpected,
    OCExpected,
    JSONSAPExpected,
    GroundTruthEntry,
    VerificationDetails,
    OCRComparison,
    StageResult,
    ExecutionLog,
)
from .ground_truth import GroundTruthManager
from .ocr_comparator import OCRComparator
from .stage_verifier import StageVerifier
from .execution_logger import ExecutionLogger

__all__ = [
    # Enums
    "StageStatus",
    "VerificationResult",
    "ExecutionResult",
    # Expected data classes
    "OCRExpected",
    "ParsingExpected",
    "ProveedorExpected",
    "OCExpected",
    "JSONSAPExpected",
    "GroundTruthEntry",
    # Result classes
    "VerificationDetails",
    "OCRComparison",
    "StageResult",
    "ExecutionLog",
    # Manager classes
    "GroundTruthManager",
    "OCRComparator",
    "StageVerifier",
    "ExecutionLogger",
]

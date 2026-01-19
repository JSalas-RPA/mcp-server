# verification/execution_logger.py
"""
Sistema de logging de ejecuciones del flujo de facturas.
"""

import json
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import asdict

from .schemas import (
    ExecutionLog,
    ExecutionResult,
    StageResult,
    StageStatus,
    VerificationResult,
)

logger = logging.getLogger(__name__)

# Ruta por defecto para logs
DEFAULT_LOGS_DIR = Path(__file__).parent.parent / "data" / "execution_logs"


class ExecutionLogger:
    """Logger de ejecuciones del flujo de facturas."""

    def __init__(self, logs_dir: Optional[str] = None):
        """
        Inicializa el logger de ejecuciones.

        Args:
            logs_dir: Directorio donde guardar los logs.
                     Si no se especifica, usa el directorio por defecto.
        """
        self.logs_dir = Path(logs_dir) if logs_dir else DEFAULT_LOGS_DIR
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        self.current_log: Optional[ExecutionLog] = None

    def start_execution(
        self,
        archivo_entrada: str,
        ground_truth_usado: Optional[str] = None,
        modo: str = "verificacion"
    ) -> str:
        """
        Inicia una nueva ejecución.

        Args:
            archivo_entrada: Nombre del archivo PDF de entrada
            ground_truth_usado: Archivo de ground truth utilizado
            modo: Modo de ejecución ("verificacion", "produccion", etc.)

        Returns:
            ID único de la ejecución
        """
        execution_id = f"exec_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        self.current_log = ExecutionLog(
            execution_id=execution_id,
            timestamp_inicio=datetime.now(),
            archivo_entrada=archivo_entrada,
            ground_truth_usado=ground_truth_usado,
            modo=modo,
        )

        logger.info(f"Ejecución iniciada: {execution_id}")
        return execution_id

    def add_stage_result(self, stage: StageResult) -> None:
        """
        Agrega el resultado de una etapa.

        Args:
            stage: Resultado de la etapa
        """
        if not self.current_log:
            raise RuntimeError("No hay ejecución activa. Llamar start_execution() primero.")

        self.current_log.etapas.append(stage)
        logger.debug(f"Etapa {stage.etapa} ({stage.nombre}) agregada: {stage.status.value}")

    def add_context(self, key: str, value: any) -> None:
        """
        Agrega contexto adicional a la ejecución.

        Args:
            key: Clave del contexto
            value: Valor del contexto
        """
        if not self.current_log:
            raise RuntimeError("No hay ejecución activa.")

        self.current_log.contexto_adicional[key] = value

    def finish_execution(self, resultado_global: Optional[ExecutionResult] = None) -> str:
        """
        Finaliza la ejecución y guarda el log.

        Args:
            resultado_global: Resultado global (si no se especifica, se calcula automáticamente)

        Returns:
            Ruta al archivo de log guardado
        """
        if not self.current_log:
            raise RuntimeError("No hay ejecución activa.")

        # Establecer tiempo de finalización
        self.current_log.timestamp_fin = datetime.now()
        self.current_log.duracion_segundos = (
            self.current_log.timestamp_fin - self.current_log.timestamp_inicio
        ).total_seconds()

        # Calcular resultado global si no se especificó
        if resultado_global:
            self.current_log.resultado_global = resultado_global
        else:
            self.current_log.resultado_global = self._calculate_global_result()

        # Generar resumen
        self.current_log.resumen = self._generate_summary()

        # Guardar log
        log_path = self._save_log()

        logger.info(f"Ejecución finalizada: {self.current_log.resultado_global.value}")

        # Limpiar log actual
        self.current_log = None

        return log_path

    def _calculate_global_result(self) -> ExecutionResult:
        """Calcula el resultado global basado en las etapas."""
        if not self.current_log.etapas:
            return ExecutionResult.ERROR

        etapas_error = sum(
            1 for e in self.current_log.etapas
            if e.status == StageStatus.ERROR
        )
        etapas_warning = sum(
            1 for e in self.current_log.etapas
            if e.verificacion and e.verificacion.resultado == VerificationResult.WARNING
        )

        if etapas_error > 0:
            return ExecutionResult.ERROR
        elif etapas_warning > 0:
            return ExecutionResult.PARTIAL
        else:
            return ExecutionResult.SUCCESS

    def _generate_summary(self) -> dict:
        """Genera resumen de la ejecución."""
        etapas_exitosas = sum(
            1 for e in self.current_log.etapas
            if e.status == StageStatus.SUCCESS
        )
        etapas_fallidas = sum(
            1 for e in self.current_log.etapas
            if e.status == StageStatus.ERROR
        )

        # Encontrar primera etapa fallida
        etapa_fallo = None
        for e in self.current_log.etapas:
            if e.status == StageStatus.ERROR:
                etapa_fallo = e.nombre
                break

        return {
            "etapas_ejecutadas": len(self.current_log.etapas),
            "etapas_exitosas": etapas_exitosas,
            "etapas_fallidas": etapas_fallidas,
            "etapa_fallo": etapa_fallo,
        }

    def _save_log(self) -> str:
        """Guarda el log a archivo JSON."""
        # Generar nombre de archivo
        timestamp = self.current_log.timestamp_inicio.strftime("%Y%m%d_%H%M%S")
        filename = f"log_{timestamp}.json"
        filepath = self.logs_dir / filename

        # Convertir a diccionario serializable
        log_dict = self._serialize_log(self.current_log)

        # Guardar
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(log_dict, f, indent=2, ensure_ascii=False, default=str)

        logger.info(f"Log guardado en: {filepath}")
        return str(filepath)

    def _serialize_log(self, log: ExecutionLog) -> dict:
        """Convierte ExecutionLog a diccionario serializable."""
        def convert_value(obj):
            if hasattr(obj, 'value'):  # Enum
                return obj.value
            elif hasattr(obj, 'isoformat'):  # datetime
                return obj.isoformat()
            elif hasattr(obj, '__dataclass_fields__'):  # dataclass
                return {k: convert_value(v) for k, v in asdict(obj).items()}
            elif isinstance(obj, list):
                return [convert_value(item) for item in obj]
            elif isinstance(obj, dict):
                return {k: convert_value(v) for k, v in obj.items()}
            return obj

        return convert_value(log)

    def get_recent_logs(self, limit: int = 10) -> list[dict]:
        """
        Obtiene los logs más recientes.

        Args:
            limit: Número máximo de logs a retornar

        Returns:
            Lista de logs (diccionarios)
        """
        log_files = sorted(
            self.logs_dir.glob("log_*.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True
        )[:limit]

        logs = []
        for filepath in log_files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    logs.append(json.load(f))
            except Exception as e:
                logger.warning(f"Error al leer log {filepath}: {e}")

        return logs

    def get_log_by_id(self, execution_id: str) -> Optional[dict]:
        """
        Obtiene un log específico por su ID.

        Args:
            execution_id: ID de la ejecución

        Returns:
            Log como diccionario o None si no se encuentra
        """
        for filepath in self.logs_dir.glob("log_*.json"):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    log = json.load(f)
                    if log.get("execution_id") == execution_id:
                        return log
            except Exception:
                continue
        return None

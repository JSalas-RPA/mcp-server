# utilities/date_utils.py
# ============================================
# Funciones de utilidad para procesamiento de fechas
# ============================================

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def format_sap_date(date_str: str) -> str | None:
    """
    Convierte cualquier formato de fecha al formato requerido por SAP (YYYY-MM-DDT00:00:00).

    Formatos soportados:
    - YYYY-MM-DD
    - DD/MM/YYYY
    - DD/MM/YYYY HH:MM
    - MM/DD/YYYY
    - DD-MM-YYYY
    - YYYY/MM/DD
    - YYYY-MM-DD HH:MM:SS
    - DD/MM/YYYY HH:MM:SS
    """
    if not date_str:
        return None

    # Si ya está en formato SAP, retornar tal cual
    if "T00:00:00" in date_str and len(date_str.split("T")[0]) == 10:
        return date_str

    date_part = date_str.split("T")[0] if "T" in date_str else date_str

    date_formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d/%m/%Y %H:%M",
        "%m/%d/%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
    ]

    for fmt in date_formats:
        try:
            dt = datetime.strptime(date_part.strip(), fmt)
            return dt.strftime("%Y-%m-%dT00:00:00")
        except ValueError:
            continue

    logger.warning(f"No se pudo parsear la fecha: {date_str}. Usando fecha actual.")
    return datetime.now().strftime("%Y-%m-%dT00:00:00")

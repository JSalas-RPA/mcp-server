# services/matchers/__init__.py
# ============================================
# Módulo de Matching para SAP
# ============================================
# Contiene la lógica de selección determinística para:
# - Órdenes de Compra (OC)
# - Entradas de Material (MIGO)
# ============================================

from services.matchers.oc_matcher import (
    SCORE_CONFIG,
    filtrar_ocs_nivel1,
    calcular_score_item,
    evaluar_ocs_nivel2,
    obtener_ordenes_compra_proveedor,
)

from services.matchers.migo_matcher import (
    MIGO_CONFIG,
    normalizar_numero_factura,
    verificar_match_header_text,
    evaluar_migos_nivel2,
    verificar_entradas_material,
)

__all__ = [
    # OC Matcher
    "SCORE_CONFIG",
    "filtrar_ocs_nivel1",
    "calcular_score_item",
    "evaluar_ocs_nivel2",
    "obtener_ordenes_compra_proveedor",
    # MIGO Matcher
    "MIGO_CONFIG",
    "normalizar_numero_factura",
    "verificar_match_header_text",
    "evaluar_migos_nivel2",
    "verificar_entradas_material",
]

# scripts/flujo_completo.py
# ============================================================================
# Script de prueba del flujo completo de procesamiento de facturas
# ============================================================================
# Uso:
#   python -m scripts.flujo_completo <ruta_pdf>
#   python -m scripts.flujo_completo <ruta_pdf> --enviar
#
# Este script ejecuta el flujo completo paso a paso:
#   1. Extraer texto del PDF via OCR
#   2. Parsear datos estructurados con OpenAI
#   3. Validar proveedor en SAP
#   4. Buscar órdenes de compra
#   5. Verificar entrada de material (MIGO)
#   6. Construir JSON para SAP
#   7. Enviar a SAP (opcional)
#   8. Notificar errores automáticamente por correo
#
# NOTA: Este script importa directamente de services/ y utilities/,
#       NO de server.py (las funciones decoradas con @mcp.tool no son callable).
# ============================================================================

import os
import sys
import json
import logging

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# IMPORTS DIRECTOS (no desde server.py)
# ============================================================================
from utilities.ocr import get_transcript_document, get_transcript_document_cloud_vision
from utilities.file_storage import download_pdf_to_tempfile
from utilities.email_client import send_email
from utilities.llm_client import extraer_datos_factura_desde_texto
from tools_sap_services.sap_operations import (
    obtener_proveedores_sap,
    buscar_proveedor_en_sap,
    construir_json_factura_sap,
)
from tools_sap_services.sap_api import enviar_factura_a_sap
from tools_sap_services.matchers import (
    obtener_ordenes_compra_proveedor,
    verificar_entradas_material,
    verificar_entradas_material_multi,
)


# ============================================================================
# FUNCIONES WRAPPER (replican la lógica de las tools del server)
# ============================================================================

def extraer_texto(ruta_gcs: str) -> dict:
    """Extrae texto de PDF via OCR."""
    ruta_temp = None
    try:
        logger.info(f"Extrayendo texto de: {ruta_gcs}")
        ruta_temp = download_pdf_to_tempfile(ruta_gcs)
        texto = get_transcript_document(ruta_temp)
        return {"status": "success", "data": texto}
    except Exception as e:
        logger.error(f"Error en extracción: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        if ruta_temp and os.path.exists(ruta_temp):
            os.remove(ruta_temp)


def parsear_factura(texto: str) -> dict:
    """Parsea datos de factura desde texto OCR."""
    try:
        datos = extraer_datos_factura_desde_texto(texto)
        if datos:
            return {"status": "success", "data": datos}
        return {"status": "error", "error": "No se pudieron extraer datos"}
    except Exception as e:
        logger.error(f"Error en parseo: {e}")
        return {"status": "error", "error": str(e)}


def validar_proveedor(factura_datos: dict) -> dict:
    """Valida proveedor en SAP."""
    try:
        proveedores = obtener_proveedores_sap()
        if not proveedores:
            return {"status": "error", "error": "No se pudieron obtener proveedores de SAP"}

        resultado = buscar_proveedor_en_sap(factura_datos, proveedores)
        if resultado:
            return {"status": "success", "data": resultado}
        return {"status": "not_found", "error": "Proveedor no encontrado en SAP"}
    except Exception as e:
        logger.error(f"Error validando proveedor: {e}")
        return {"status": "error", "error": str(e)}


def buscar_ordenes_compra(factura_datos: dict, supplier_code: str) -> dict:
    """Busca órdenes de compra para un proveedor."""
    try:
        resultado = obtener_ordenes_compra_proveedor(factura_datos, supplier_code)
        return resultado  # Ya viene con formato {status, data, ...}
    except Exception as e:
        logger.error(f"Error buscando OCs: {e}")
        return {"status": "error", "error": str(e)}


def verificar_migo(factura_datos: dict, oc_info: dict) -> dict:
    """Verifica entrada de material (MIGO) para un solo item."""
    try:
        resultado = verificar_entradas_material(factura_datos, oc_info)
        return resultado  # Ya viene con formato {status, data, ...}
    except Exception as e:
        logger.error(f"Error verificando MIGO: {e}")
        return {"status": "error", "error": str(e)}


def verificar_migo_multi(factura_datos: dict, oc_items: list) -> dict:
    """Verifica entrada de material (MIGO) para múltiples items."""
    try:
        resultado = verificar_entradas_material_multi(factura_datos, oc_items)
        return resultado  # Ya viene con formato {status, reference_documents, ...}
    except Exception as e:
        logger.error(f"Error verificando MIGO multi-item: {e}")
        return {"status": "error", "error": str(e)}


def construir_json(
    factura_datos: dict,
    proveedor_info: dict,
    oc_items: list,
    needs_migo: bool = False,
    reference_document: dict | list = None
) -> dict:
    """Construye JSON para SAP. reference_document puede ser dict o lista de dicts."""
    try:
        resultado = construir_json_factura_sap(
            factura_datos, proveedor_info, oc_items, needs_migo, reference_document
        )
        if resultado:
            return {"status": "success", "data": resultado}
        return {"status": "error", "error": "No se pudo construir JSON"}
    except Exception as e:
        logger.error(f"Error construyendo JSON: {e}")
        return {"status": "error", "error": str(e)}


def enviar_a_sap(factura_json: dict) -> dict:
    """Envía factura a SAP."""
    try:
        resultado = enviar_factura_a_sap(factura_json)
        resultado = resultado.get("d", {})
        if resultado.get("SupplierInvoiceStatus") == "5":
            logger.info(f"Número de factura en SAP: {resultado.get('SupplierInvoice')}")
            return {"status": "success", "data": resultado}
        return {"status": "error", "error": "No se pudo enviar a SAP"}
    except Exception as e:
        logger.error(f"Error enviando a SAP: {e}")
        return {"status": "error", "error": str(e)}


def enviar_correo(destinatario: str = None, asunto: str = "", cuerpo: str = "") -> dict:
    """Envía correo de notificación."""
    try:
        resultado = send_email(destinatario, asunto, cuerpo)
        if resultado:
            return {"status": "success", "data": resultado}
        return {"status": "error", "error": "No se pudo enviar correo"}
    except Exception as e:
        logger.error(f"Error enviando correo: {e}")
        return {"status": "error", "error": str(e)}


# ============================================================================
# EJECUCIÓN DE PASOS CON NOTIFICACIÓN AUTOMÁTICA
# ============================================================================

class FlujoContext:
    """Contexto del flujo para tracking de errores."""
    def __init__(self, archivo_origen: str):
        self.archivo_origen = archivo_origen
        self.datos_factura = None
        self.proveedor_info = None
        self.oc_info = None

    def get_contexto(self) -> dict:
        """Retorna contexto acumulado para notificaciones."""
        ctx = {}
        if self.datos_factura:
            ctx["Proveedor"] = self.datos_factura.get("SupplierName", "N/A")
            ctx["NIT"] = self.datos_factura.get("SupplierTaxNumber", "N/A")
            ctx["Monto"] = self.datos_factura.get("InvoiceGrossAmount", "N/A")
            ctx["Factura"] = self.datos_factura.get("SupplierInvoiceIDByInvcgParty", "N/A")
        if self.proveedor_info:
            ctx["Proveedor SAP"] = self.proveedor_info.get("Supplier", "N/A")
        if self.oc_info:
            ctx["OC"] = self.oc_info.get("selected_purchase_order", "N/A")
        return ctx


def ejecutar_paso(
    nombre_paso: str,
    funcion,
    *args,
    contexto: FlujoContext = None,
    contexto_extra: dict = None,
    **kwargs
) -> dict:
    """
    Ejecuta un paso del flujo y notifica automáticamente si falla.

    Args:
        nombre_paso: Nombre descriptivo del paso
        funcion: Función a ejecutar
        *args: Argumentos para la función
        contexto: Contexto del flujo (para datos acumulados)
        contexto_extra: Datos adicionales específicos de este paso
        **kwargs: Keyword arguments para la función

    Returns:
        dict con el resultado de la función
    """
    try:
        resultado = funcion(*args, **kwargs)
    except Exception as e:
        resultado = {"status": "error", "error": str(e)}

    # Si falló, notificar
    status = resultado.get("status", "error")
    if status not in ["success"]:
        _notificar_error(
            paso=nombre_paso,
            error=resultado.get("error", "Error desconocido"),
            contexto=contexto,
            contexto_extra=contexto_extra
        )

    return resultado


def _notificar_error(
    paso: str,
    error: str,
    contexto: FlujoContext = None,
    contexto_extra: dict = None
):
    """Envía notificación por correo cuando ocurre un error."""
    asunto = f"[MCP-SAP] Error en {paso}"

    cuerpo_lines = [
        "Se produjo un error durante el procesamiento de factura.",
        "",
        f"PASO: {paso}",
        f"ERROR: {error}",
        "",
    ]

    if contexto:
        cuerpo_lines.append(f"ARCHIVO: {contexto.archivo_origen}")
        cuerpo_lines.append("")
        ctx_data = contexto.get_contexto()
        if ctx_data:
            cuerpo_lines.append("DATOS ACUMULADOS:")
            for key, value in ctx_data.items():
                cuerpo_lines.append(f"  • {key}: {value}")
            cuerpo_lines.append("")

    if contexto_extra:
        cuerpo_lines.append("CONTEXTO ADICIONAL:")
        for key, value in contexto_extra.items():
            str_value = str(value)
            if len(str_value) > 200:
                str_value = str_value[:200] + "..."
            cuerpo_lines.append(f"  • {key}: {str_value}")

    cuerpo = "\n".join(cuerpo_lines)

    print(f"\n📧 Enviando notificación de error...")
    resultado = enviar_correo(asunto=asunto, cuerpo=cuerpo)

    if resultado.get("status") == "success":
        print(f"   ✅ Notificación enviada")
    else:
        print(f"   ⚠️  No se pudo enviar notificación: {resultado.get('error')}")


# ============================================================================
# FUNCIONES DE UTILIDAD PARA IMPRIMIR
# ============================================================================

def print_header(step, title: str):
    """Imprime un header para cada paso."""
    print("\n" + "=" * 70)
    print(f"PASO {step}: {title}")
    print("=" * 70)


def print_result(resultado: dict, show_data: bool = True):
    """Imprime el resultado de una operación."""
    status = resultado.get('status', 'unknown')

    if status == 'success':
        print(f"✅ Status: {status}")
        if show_data and 'data' in resultado:
            data = resultado['data']
            if isinstance(data, dict):
                print("📋 Datos:")
                for key, value in data.items():
                    str_value = str(value)
                    if len(str_value) > 100:
                        str_value = str_value[:100] + "..."
                    print(f"   • {key}: {str_value}")
            elif isinstance(data, list):
                print(f"📋 {len(data)} elementos encontrados")
                for i, item in enumerate(data[:5]):
                    print(f"   {i+1}. {item}")
            else:
                print(f"📋 Datos: {str(data)[:500]}...")
    elif status == 'not_found':
        print(f"⚠️  Status: {status}")
        print(f"   Mensaje: {resultado.get('error', 'No encontrado')}")
    else:
        print(f"❌ Status: {status}")
        print(f"   Error: {resultado.get('error', 'Error desconocido')}")

    return status == 'success'


# ============================================================================
# FLUJO PRINCIPAL
# ============================================================================

def ejecutar_flujo_completo(source: str, enviar: bool = False):
    """
    Ejecuta el flujo completo de procesamiento de factura paso a paso.

    Args:
        source: Ruta al PDF (local, gs://, https://)
        enviar: Si True, envía la factura a SAP. Si False, solo construye el JSON.
    """
    print("\n" + "=" * 70)
    print("🚀 INICIANDO FLUJO COMPLETO DE PROCESAMIENTO DE FACTURA")
    print("=" * 70)
    print(f"📁 Archivo: {source}")
    print(f"📤 Enviar a SAP: {'Sí' if enviar else 'No (solo simulación)'}")
    print("=" * 70)

    # Contexto para tracking de errores
    ctx = FlujoContext(archivo_origen=source)

    # =========================================================================
    # PASO 1: Extraer texto del PDF
    # =========================================================================
    print_header(1, "EXTRACCIÓN DE TEXTO (OCR)")
    print(f"Extrayendo texto de: {source}")

    resultado = ejecutar_paso("Extracción de texto (OCR)", extraer_texto, source, contexto=ctx)
    if not print_result(resultado, show_data=False):
        print("❌ No se pudo extraer texto. Abortando flujo.")
        return False

    texto_extraido = resultado['data']
    print(f"📄 Texto extraído: {len(texto_extraido)} caracteres")
    print(f"   Preview: {texto_extraido[:300]}...")

    # =========================================================================
    # PASO 2: Parsear datos de la factura
    # =========================================================================
    print_header(2, "PARSING DE DATOS DE FACTURA")
    print("Extrayendo datos estructurados con OpenAI...")

    resultado = ejecutar_paso(
        "Parsing de datos de factura",
        parsear_factura,
        texto_extraido,
        contexto=ctx,
        contexto_extra={"texto_preview": texto_extraido[:300]}
    )
    if not print_result(resultado):
        print("❌ No se pudieron parsear los datos. Abortando flujo.")
        return False

    ctx.datos_factura = resultado['data']

    # =========================================================================
    # PASO 3: Validar proveedor en SAP
    # =========================================================================
    print_header(3, "VALIDACIÓN DE PROVEEDOR EN SAP")

    resultado = ejecutar_paso(
        "Validación de proveedor en SAP",
        validar_proveedor,
        ctx.datos_factura,
        contexto=ctx
    )
    if not print_result(resultado):
        print("❌ Proveedor no encontrado en SAP. Abortando flujo.")
        return False

    ctx.proveedor_info = resultado['data']

    # =========================================================================
    # PASO 4: Obtener órdenes de compra (Selección Determinística)
    # =========================================================================
    print_header(4, "BÚSQUEDA DE ÓRDENES DE COMPRA")

    supplier_code = ctx.proveedor_info.get('Supplier', '')

    print(f"Proveedor SAP: {supplier_code}")
    print(f"Monto factura: {ctx.datos_factura.get('InvoiceGrossAmount', 0.0)}")

    resultado = ejecutar_paso(
        "Búsqueda de órdenes de compra",
        buscar_ordenes_compra,
        ctx.datos_factura,
        supplier_code,
        contexto=ctx
    )

    if resultado.get('status') == 'duplicate_requires_intervention':
        print("⚠️  Múltiples OCs con score similar, requiere intervención manual:")
        for i, cand in enumerate(resultado.get('candidatos', [])[:3]):
            print(f"   {i+1}. OC {cand.get('selected_purchase_order')} - Score: {cand.get('match_score', 0):.1f}")
        return False

    if not print_result(resultado):
        print("❌ No se encontraron OCs para este proveedor. Abortando flujo.")
        return False

    # Extraer datos de la selección
    oc_data = resultado.get('data', resultado)
    ctx.oc_info = oc_data
    oc_items = oc_data.get('oc_items', [])
    needs_migo = oc_data.get('needs_migo', False)
    match_score = oc_data.get('match_score', 0)
    selected_oc = oc_data.get('selected_purchase_order', '')
    selected_oc_item = oc_data.get('selected_purchase_order_item', '')

    # Obtener material de la OC
    material_oc = ""
    if oc_items:
        material_oc = oc_items[0].get("Material", "")

    print(f"\n📊 OC Seleccionada: {selected_oc}")
    print(f"   Score: {match_score:.1f}/100")
    print(f"   Incluir ReferenceDocument: {'Sí' if needs_migo else 'No'}")

    # =========================================================================
    # PASO 4.5: VERIFICACIÓN OBLIGATORIA DE ENTRADA DE MATERIAL (MIGO)
    # =========================================================================
    print_header("4.5", "VERIFICACIÓN DE ENTRADA DE MATERIAL (MIGO) - OBLIGATORIA")

    # Verificar si hay múltiples items
    es_multi_item = len(oc_items) > 1

    if es_multi_item:
        # MODO MULTI-ITEM: Verificar MIGO para cada item de la OC
        print(f"   Modo multi-item: {len(oc_items)} items a verificar")

        resultado_migo = ejecutar_paso(
            "Verificación de entrada de material (MIGO) - Multi-item",
            verificar_migo_multi,
            ctx.datos_factura,
            oc_items,
            contexto=ctx
        )
    else:
        # MODO SINGLE: Verificación de un solo item (comportamiento original)
        oc_info_para_migo = {
            "PurchaseOrder": selected_oc,
            "PurchaseOrderItem": selected_oc_item,
            "Material": material_oc
        }

        resultado_migo = ejecutar_paso(
            "Verificación de entrada de material (MIGO)",
            verificar_migo,
            ctx.datos_factura,
            oc_info_para_migo,
            contexto=ctx
        )

    if resultado_migo.get("status") not in ["success"]:
        error_msg = resultado_migo.get("error", "No se encontró entrada de material")
        print(f"❌ {error_msg}")
        print("   No se puede facturar un producto que no ha llegado a almacén.")
        return False

    migo_data = resultado_migo.get('data', resultado_migo)
    print(f"✅ MIGO verificado correctamente")
    print(f"   Cantidad disponible: {migo_data.get('cantidad_disponible', 'N/A')}")
    print(f"   Score MIGO: {migo_data.get('match_score', 0):.1f}/100")

    # Obtener reference_document(s) si needs_migo es True
    reference_documents = None
    if needs_migo:
        if es_multi_item:
            # Multi-item: obtener lista de reference_documents
            reference_documents = migo_data.get("reference_documents", [])
            if reference_documents:
                print(f"   ReferenceDocuments ({len(reference_documents)} items):")
                for idx, ref_doc in enumerate(reference_documents, 1):
                    if ref_doc:
                        print(f"      Item {idx}: {ref_doc.get('ReferenceDocument')} (se incluirá en JSON)")
                    else:
                        print(f"      Item {idx}: [FALTA MIGO]")
        else:
            # Single: obtener un solo reference_document
            reference_documents = migo_data.get("reference_document")
            if reference_documents:
                print(f"   ReferenceDocument: {reference_documents.get('ReferenceDocument')} (se incluirá en JSON)")
    else:
        print(f"   ReferenceDocument: No se incluirá en JSON")

    # =========================================================================
    # PASO 5: Construir JSON para SAP
    # =========================================================================
    print_header(5, "CONSTRUCCIÓN DE JSON PARA SAP")
    print("Construyendo payload para SAP...")

    resultado = ejecutar_paso(
        "Construcción de JSON para SAP",
        construir_json,
        ctx.datos_factura,
        ctx.proveedor_info,
        oc_items,
        contexto=ctx,
        needs_migo=needs_migo,
        reference_document=reference_documents
    )
    if not print_result(resultado, show_data=False):
        print("❌ No se pudo construir el JSON. Abortando flujo.")
        return False

    factura_json = resultado['data']

    # Mostrar JSON completo
    print("\n📄 JSON CONSTRUIDO:")
    print("-" * 50)
    print(json.dumps(factura_json, indent=2, ensure_ascii=False))
    print("-" * 50)

    # =========================================================================
    # PASO 6: Enviar a SAP (opcional)
    # =========================================================================
    print_header(6, "ENVÍO A SAP")

    if not enviar:
        print("⏸️  Modo simulación: No se enviará a SAP")
        print("   Para enviar, ejecutar con --enviar")
    else:
        print("📤 Enviando factura a SAP...")

        resultado = ejecutar_paso(
            "Envío a SAP",
            enviar_a_sap,
            factura_json,
            contexto=ctx
        )
        if not print_result(resultado):
            print("❌ Error al enviar a SAP.")
            return False

        print("🎉 Factura enviada exitosamente a SAP!")

    # =========================================================================
    # RESUMEN FINAL
    # =========================================================================
    print("\n" + "=" * 70)
    print("📊 RESUMEN DEL PROCESO")
    print("=" * 70)
    print(f"✅ Texto extraído: {len(texto_extraido)} caracteres")
    print(f"✅ Proveedor: {ctx.proveedor_info.get('SupplierName')} ({ctx.proveedor_info.get('Supplier')})")
    print(f"✅ NIT: {ctx.proveedor_info.get('TaxNumber')}")
    print(f"✅ Factura N°: {factura_json.get('SupplierInvoiceIDByInvcgParty')}")
    print(f"✅ Monto: {factura_json.get('InvoiceGrossAmount')} {factura_json.get('DocumentCurrency')}")
    print(f"✅ Fecha: {factura_json.get('DocumentDate')}")
    print(f"✅ OCs asociadas: {len(oc_items)}")
    print(f"{'✅' if enviar else '⏸️ '} Enviado a SAP: {'Sí' if enviar else 'No (simulación)'}")
    print("=" * 70)

    # Guardar resultados
    resultado_final = {
        'success': True,
        'datos_factura': ctx.datos_factura,
        'proveedor': ctx.proveedor_info,
        'ordenes_compra': oc_items,
        'json_sap': factura_json,
        'enviado': enviar
    }

    os.makedirs("data", exist_ok=True)
    with open("data/resultado_flujo.json", "w", encoding="utf-8") as f:
        json.dump(resultado_final, f, indent=2, ensure_ascii=False)
    print("💾 Resultado guardado en 'data/resultado_flujo.json'")

    return True


def main():
    """Punto de entrada principal."""
    if len(sys.argv) < 2:
        print("=" * 70)
        print("📋 USO DEL SCRIPT")
        print("=" * 70)
        print("python -m scripts.flujo_completo <ruta_pdf> [--enviar]")
        print()
        print("Argumentos:")
        print("  <ruta_pdf>   Ruta al archivo PDF (local, gs://, https://)")
        print("  --enviar     Enviar la factura a SAP (opcional)")
        print()
        print("Ejemplos:")
        print("  python -m scripts.flujo_completo /ruta/factura.pdf")
        print("  python -m scripts.flujo_completo gs://bucket/factura.pdf")
        print("  python -m scripts.flujo_completo factura.pdf --enviar")
        print("=" * 70)
        sys.exit(1)

    source = sys.argv[1]
    enviar = "--enviar" in sys.argv or "-e" in sys.argv

    try:
        success = ejecutar_flujo_completo(source, enviar)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Proceso interrumpido por el usuario")
        sys.exit(130)
    except Exception as e:
        # Error no manejado (fuera del flujo normal)
        print(f"\n❌ Error inesperado: {e}")
        logger.exception(e)
        _notificar_error(
            paso="Error inesperado en el flujo",
            error=str(e),
            contexto=FlujoContext(archivo_origen=source)
        )
        sys.exit(1)


if __name__ == "__main__":
    main()

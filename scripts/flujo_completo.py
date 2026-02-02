# scripts/flujo_completo_2.py
# ============================================================================
# Script de prueba del flujo completo usando las nuevas tools modulares
# ============================================================================
# Uso:
#   python -m scripts.flujo_completo_2 <ruta_pdf>
#   python -m scripts.flujo_completo_2 gs://bucket/factura.pdf
#   python -m scripts.flujo_completo_2 /ruta/local/factura.pdf
#
# Este script ejecuta cada tool por separado para mostrar el flujo paso a paso:
#   1. extraer_texto_pdf() - Extrae texto del PDF via OCR
#   2. parsear_datos_factura() - Estructura los datos extraídos
#   3. validar_proveedor_sap() - Valida proveedor en SAP
#   4. obtener_ordenes_compra() - Busca OCs del proveedor
#   5. construir_json_factura() - Construye JSON para SAP
#   6. enviar_factura_sap() - Envía a SAP (opcional)
# ============================================================================

import sys
import json
import logging

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Importar las tools desde el catálogo
from server import (
    enviar_correo,
    extraer_texto,
    parsear_factura,
    validar_proveedor,
    buscar_ordenes_compra,
    verificar_migo,
    construir_json,
    enviar_a_sap,
    send_email,
)


def print_header(step: int, title: str):
    """Imprime un header para cada paso."""
    print("\n" + "=" * 70)
    print(f"PASO {step}: {title}")
    print("=" * 70)


def print_result(resultado: dict, show_data: bool = True):
    """Imprime el resultado de una tool."""
    status = resultado.get('status', 'unknown')

    if status == 'success':
        print(f"✅ Status: {status}")
        if show_data and 'data' in resultado:
            data = resultado['data']
            if isinstance(data, dict):
                print("📋 Datos:")
                for key, value in data.items():
                    # Truncar valores largos
                    str_value = str(value)
                    if len(str_value) > 100:
                        str_value = str_value[:100] + "..."
                    print(f"   • {key}: {str_value}")
            elif isinstance(data, list):
                print(f"📋 {len(data)} elementos encontrados")
                for i, item in enumerate(data[:5]):  # Mostrar máx 5
                    print(f"   {i+1}. {item}")
            else:
                # Es texto (como el OCR)
                print(f"📋 Datos: {str(data)[:500]}...")
    elif status == 'not_found':
        print(f"⚠️  Status: {status}")
        print(f"   Mensaje: {resultado.get('error', 'No encontrado')}")
    else:
        print(f"❌ Status: {status}")
        print(f"   Error: {resultado.get('error', 'Error desconocido')}")

    return status == 'success'


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

    # Variables para almacenar resultados intermedios
    texto_extraido = None
    datos_factura = None
    proveedor_info = None
    oc_items = None
    factura_json = None

    # =========================================================================
    # PASO 1: Extraer texto del PDF
    # =========================================================================
    print_header(1, "EXTRACCIÓN DE TEXTO (OCR)")
    print(f"Extrayendo texto de: {source}")

    resultado = extraer_texto(source)
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

    resultado = parsear_factura(texto_extraido)
    if not print_result(resultado):
        print("❌ No se pudieron parsear los datos. Abortando flujo.")
        return False

    datos_factura = resultado

    # =========================================================================
    # PASO 3: Validar proveedor en SAP
    # =========================================================================
    print_header(3, "VALIDACIÓN DE PROVEEDOR EN SAP")

    resultado = validar_proveedor(datos_factura)
    if not print_result(resultado):
        print("❌ Proveedor no encontrado en SAP. Abortando flujo.")
        return False

    proveedor_info = resultado['data']

    # =========================================================================
    # PASO 4: Obtener órdenes de compra (Selección Determinística)
    # =========================================================================
    print_header(4, "BÚSQUEDA DE ÓRDENES DE COMPRA")

    supplier_code = proveedor_info.get('Supplier', '')

    print(f"Proveedor SAP: {supplier_code}")
    print(f"Monto factura: {datos_factura.get('InvoiceGrossAmount', 0.0)}")

    # Nueva llamada con datos completos de factura para scoring
    resultado = buscar_ordenes_compra(datos_factura, supplier_code)

    if resultado.get('status') == 'duplicate_requires_intervention':
        print("⚠️  Múltiples OCs con score similar, requiere intervención manual:")
        for i, cand in enumerate(resultado.get('candidatos', [])[:3]):
            print(f"   {i+1}. OC {cand.get('selected_purchase_order')} - Score: {cand.get('match_score', 0):.1f}")
        return False

    if not print_result(resultado):
        print("❌ No se encontraron OCs para este proveedor. Abortando flujo.")
        return False

    # Extraer datos de la selección
    oc_data = resultado['data']
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

    oc_info_para_migo = {
        "PurchaseOrder": selected_oc,
        "PurchaseOrderItem": selected_oc_item,
        "Material": material_oc
    }

    resultado_migo = verificar_migo(datos_factura, oc_info_para_migo)

    if resultado_migo.get("status") != "success":
        error_msg = resultado_migo.get("error", "No se encontró entrada de material")
        print(f"❌ {error_msg}")
        print("   No se puede facturar un producto que no ha llegado a almacén.")
        return False

    print(f"✅ MIGO verificado correctamente")
    print(f"   Cantidad disponible: {resultado_migo.get('cantidad_disponible', 'N/A')}")
    print(f"   Score MIGO: {resultado_migo.get('match_score', 0):.1f}/100")

    # Solo usar reference_document si needs_migo es True
    reference_document = None
    if needs_migo:
        reference_document = resultado_migo.get("reference_document")
        print(f"   ReferenceDocument: {reference_document.get('ReferenceDocument')} (se incluirá en JSON)")
    else:
        print(f"   ReferenceDocument: No se incluirá en JSON")

    # =========================================================================
    # PASO 5: Construir JSON para SAP
    # =========================================================================
    print_header(5, "CONSTRUCCIÓN DE JSON PARA SAP")
    print("Construyendo payload para SAP...")

    resultado = construir_json(
        datos_factura,
        proveedor_info,
        oc_items,
        needs_migo=needs_migo,
        reference_document=reference_document
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

        resultado = enviar_a_sap(factura_json)
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
    print(f"✅ Proveedor: {proveedor_info.get('SupplierName')} ({proveedor_info.get('Supplier')})")
    print(f"✅ NIT: {proveedor_info.get('TaxNumber')}")
    print(f"✅ Factura N°: {factura_json.get('SupplierInvoiceIDByInvcgParty')}")
    print(f"✅ Monto: {factura_json.get('InvoiceGrossAmount')} {factura_json.get('DocumentCurrency')}")
    print(f"✅ Fecha: {factura_json.get('DocumentDate')}")
    print(f"✅ OCs asociadas: {len(oc_items)}")
    print(f"{'✅' if enviar else '⏸️ '} Enviado a SAP: {'Sí' if enviar else 'No (simulación)'}")
    print("=" * 70)

    # Guardar resultados
    resultado_final = {
        'success': True,
        'datos_factura': datos_factura,
        'proveedor': proveedor_info,
        'ordenes_compra': oc_items,
        'json_sap': factura_json,
        'enviado': enviar
    }

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
        print("python -m scripts.flujo_completo_2 <ruta_pdf> [--enviar]")
        print()
        print("Argumentos:")
        print("  <ruta_pdf>   Ruta al archivo PDF (local, gs://, https://)")
        print("  --enviar     Enviar la factura a SAP (opcional)")
        print()
        print("Ejemplos:")
        print("  python -m scripts.flujo_completo_2 /ruta/factura.pdf")
        print("  python -m scripts.flujo_completo_2 gs://bucket/factura.pdf")
        print("  python -m scripts.flujo_completo_2 factura.pdf --enviar")
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
        print(f"\n❌ Error inesperado: {e}")
        enviar_correo(
            subject="Error en flujo completo de procesamiento de factura",
            body=f"Ocurrió un error inesperado:\n\n{str(e)}"
        )
        logger.exception(e)
        sys.exit(1)


if __name__ == "__main__":
    main()

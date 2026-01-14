from asyncio.log import logger
import sys
import json
from server import extraer_texto_pdf, procesar_factura_completa

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python -m scripts.test_extraer_datos <ruta_local|url_https|gs://...>")
        raise SystemExit(1)
    source = sys.argv[1]

    try:
        # Extraer texto de la factura
        texto_factura = extraer_texto_pdf(source)
        # Procesar la factura completa
        resultado = procesar_factura_completa(texto_factura)
        
        # Mostrar resultados
        print("\n" + "="*70)
        print("📊 RESULTADO FINAL DEL PROCESO:")
        print("="*70)
        
        if resultado['success']:
            print("✅ PROCESO COMPLETADO CON ÉXITO")
            print(f"   Factura ID: {resultado['data']['factura_id']}")
            print(f"   Proveedor: {resultado['data']['proveedor']}")
            print(f"   Código Proveedor SAP: {resultado['data']['proveedor_codigo']}")
            print(f"   Código Autorización: {resultado['data']['codigo_autorizacion'][:50]}...")
            print(f"   Monto: {resultado['data']['monto']} BOB")
            print(f"   Órdenes de Compra: {resultado['data']['oc_count']}")
            
            # Mostrar el JSON final completo automáticamente
            print("\n" + "="*70)
            print("📄 JSON FINAL ENVIADO A SAP:")
            print("="*70)
            print(json.dumps(resultado['data']['json_final'], indent=2, ensure_ascii=False))
            print("="*70)
        else:
            print("❌ PROCESO FINALIZADO CON ERROR")
            print(f"   Error: {resultado['error']}")
            print(f"   Mensaje: {resultado['message']}")
        print("="*70)
        
        # Guardar resultado en archivo para análisis
        with open("resultado_proceso.json", "w", encoding="utf-8") as f:
            json.dump(resultado, f, indent=2, ensure_ascii=False)
        print("✓ Resultado guardado en 'resultado_proceso.json'")
        
    except FileNotFoundError:
        print("❌ Error: No se encontró el archivo 'factura_texto.txt'")
        print("   Crea un archivo con el texto de la factura o ajusta la ruta.")
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        
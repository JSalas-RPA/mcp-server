import sys
import json
from server import extraer_datos_factura

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python -m scripts.test_extraer_datos <ruta_local|url_https|gs://...>")
        raise SystemExit(1)
    source = sys.argv[1]
    resultado = extraer_datos_factura(source)
    print("Resultado de la extracción de datos:")
    print(json.dumps(resultado, indent=2, ensure_ascii=False))


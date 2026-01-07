# scripts/test_ocr.py
import sys
from utilities.general import get_transcript_document_cloud_vision

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python scripts/test_ocr.py ruta/a/factura.pdf")
        raise SystemExit(1)
    print(get_transcript_document_cloud_vision(sys.argv[1]))
import logging
import sys, os, dotenv, tempfile, json
import requests

from urllib.parse import urlparse, unquote
from utilities.general import get_transcript_document_cloud_vision
from scripts.text_extractor import process_invoice_with_llm
from utilities.image_storage import download_pdf_to_tempfile

logger = logging.getLogger(__name__)

# intentamos importar util de storage si está disponible
try:
    from google.cloud import storage
except Exception:
    storage = None

# Intentar cargar .env si python-dotenv está instalado
try:
    from dotenv import load_dotenv
    load_dotenv()  # carga variables desde .env al entorno
except Exception:
    pass

# Leer el contenido del secret desde la variable de entorno
MY_API_KEY = os.getenv("API_OPENAI_KEY")

if not MY_API_KEY:
    raise EnvironmentError("No se encontró la variable de entorno 'API_OPENAI_KEY'")

def download_via_requests(url):
    r = requests.get(url, stream=True)
    r.raise_for_status()
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    with open(tf.name, "wb") as f:
        for chunk in r.iter_content(1024*1024):
            if chunk:
                f.write(chunk)
    return tf.name

def download_via_gcs_url(url):
    # soporta https://storage.googleapis.com/bucket/path... y gs://bucket/path...
    parsed = urlparse(url)
    if parsed.scheme == "gs":
        bucket = parsed.netloc
        blob_path = parsed.path.lstrip("/")
    else:
        # ejemplo: https://storage.googleapis.com/bucket/path...
        parts = parsed.path.lstrip("/").split("/", 1)
        if len(parts) < 2:
            raise ValueError("URL GCS inválida")
        bucket = parts[0]
        blob_path = parts[1]
    if storage is None:
        raise RuntimeError("google.cloud.storage no está disponible en el entorno")
    client = storage.Client()
    bucket_obj = client.bucket(bucket)
    blob = bucket_obj.blob(unquote(blob_path))
    print(f"Blob encontrado, iniciando descarga... {blob.name}")
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    blob.download_to_filename(tf.name)
    return tf.name

if __name__ == "__main__":
   
    if len(sys.argv) < 2:
        print("Uso: python scripts/test_ocr.py <ruta_local|url_https|gs://...>")
        raise SystemExit(1)

    source = sys.argv[1]

    #si es ruta local existente
    if os.path.exists(source):
        pdf_path = source
    else:
        src_lower = source.lower()
        if src_lower.startswith("http://") or src_lower.startswith("https://"):
            # primer intento: requests (funciona si el objeto es público)
            try:
                print("Descargando vía HTTP(S)...")
                pdf_path = download_via_requests(source)
            except Exception as e:
                print(f"Descarga HTTP falló: {e}. Intentando con cliente GCS si aplica...")
                # si es URL de storage.googleapis.com, intentar con cliente GCS
                if "storage.googleapis.com" in source or "storage.cloud.google.com" in source:
                    pdf_path = download_via_gcs_url(source)
                else:
                    raise
        elif src_lower.startswith("gs://"):
            print("Descargando vía cliente GCS (gs://)...")
            pdf_path = download_via_gcs_url(source)
        else:
            raise ValueError("Ruta no válida o archivo no encontrado")

    # # descarga el PDF a un temporal
    # logger.info(f"Descargando el PDF en la ruta temporal desde: {source} ...")
    # pdf_path = download_pdf_to_tempfile(source)

    try:
        print(f"PDF descargado en: {pdf_path}")
        text = get_transcript_document_cloud_vision(pdf_path)
        print("=== TEXTO EXTRAÍDO ===\n")
        print(text)
    finally:
        # opcional: eliminar temporal si fue descargado por el script
        if not os.path.exists(source) and os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
            except Exception:
                pass

    if "ERROR" in text:
        print("Error al extraer texto del documento.")
    else:
        print("Enviando al LLM...")
        result = process_invoice_with_llm(text, MY_API_KEY)
        print("\n=== RESULTADO DE EXTRACCIÓN ===\n")
        print(json.dumps(result, indent=4, ensure_ascii=False))
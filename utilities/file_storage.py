import os
import tempfile
import time, re, base64, shutil
from urllib.parse import unquote, urlparse

from google.api_core import exceptions
from google.cloud import storage
import requests

# Configurar cliente de GCS
BUCKET_NAME = os.getenv("BUCKET_NAME", "rpa_facturacion")


_storage_client = None

def get_storage_client():
    global _storage_client
    if _storage_client is None:
        _storage_client = storage.Client()
    return _storage_client

# -----------------------------
# Funciones de almacenamiento
# -----------------------------

def upload_file_base64_to_gcs(user_email: str, file_base64: str):
    """
    Sube un archivo desde base64 a GCS, creando carpeta por usuario y generando nombre automáticamente.
    Devuelve la URL pública del archivo.
    """
    try:
        # Detectar content-type si el base64 tiene prefijo data:...;base64
        match = re.match(r'data:(.*?);base64,', file_base64)
        if match:
            content_type = match.group(1)
            file_data = base64.b64decode(file_base64.split(',', 1)[1])
        else:
            # Si no hay prefijo, asumimos PDF
            content_type = "application/pdf"
            file_data = base64.b64decode(file_base64)


        # Extensión del archivo
        file_extension = content_type.split('/')[-1]

        # Nombre del archivo igual que tu ejemplo
        file_name = f"{user_email}/{content_type.split('/')[0]}_{int(time.time())}.{file_extension}"

        # Subir a GCS
        bucket = get_storage_client().bucket(BUCKET_NAME)
        blob = bucket.blob(file_name)
        blob.upload_from_string(file_data, content_type=content_type)
        blob.make_public()  # para obtener URL pública

        print(f"{content_type.split('/')[0]} subida a gs://{BUCKET_NAME}/{file_name}")
        return file_name
    except Exception as e:
        print(f"Error al subir archivo a GCS: {e}")
        return None


def _download_blob_to_tempfile(bucket_name: str, blob_path: str) -> str:
    client =get_storage_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(unquote(blob_path))
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    blob.download_to_filename(temp_file.name)
    return temp_file.name


def _download_http_to_tempfile(url: str) -> str:
    response = requests.get(url, stream=True, timeout=30, verify=False)
    response.raise_for_status()
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    with open(temp_file.name, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    return temp_file.name


def download_pdf_to_tempfile(source: str, bucket_name: str | None = None) -> str:
    """
    Descarga un PDF a un fichero temporal y devuelve su ruta.
    Soporta:
      - ruta local existente
      - gs://bucket/path/to/file.pdf
      - https://storage.googleapis.com/bucket/path/to/file.pdf
      - blob relativo (ej: 'entrada_facturas/archivo.pdf') -> usa BUCKET_NAME o bucket_name
      - cualquier http/https público
    Preferencia: usa GCS client (autenticado) cuando sea posible (gs:// o storage.googleapis.com o blob relativo).
    """
    # local file
    if os.path.exists(source):
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        shutil.copy(source, temp_file.name)
        return temp_file.name

    src = source.strip()

    # gs://bucket/path
    if src.startswith("gs://"):
        parsed = urlparse(src)
        bucket = parsed.netloc
        blob_path = parsed.path.lstrip("/")
        return _download_blob_to_tempfile(bucket, blob_path)

    # https://storage.googleapis.com/bucket/path... or storage.cloud.google.com
    parsed = urlparse(src)
    if parsed.scheme in ("http", "https") and ("storage.googleapis.com" in parsed.netloc or "storage.cloud.google.com" in parsed.netloc):
        parts = parsed.path.lstrip("/").split("/", 1)
        if len(parts) >= 2:
            bucket, blob_path = parts[0], parts[1]
            return _download_blob_to_tempfile(bucket, blob_path)
        # si no parsea bien, caemos a http

    # http(s) público
    if parsed.scheme in ("http", "https"):
        return _download_http_to_tempfile(src)

    # blob relativo dentro del bucket configurado
    target_bucket = bucket_name or BUCKET_NAME
    return _download_blob_to_tempfile(target_bucket, src)
import tempfile
from google.cloud import storage
import shutil
import os

# from src.utilities.config import load_config
# # from src.preprocessing_images import extract_signature, clean_signature, analizar_documento_google, generateScore

# config = load_config("config.yaml")

# TWILIO_ACCOUNT_SID = config['twilio']['account_sid']
# TWILIO_AUTH_TOKEN = config['twilio']['auth_token']

# # Configurar cliente de GCS
BUCKET_NAME = os.getenv("BUCKET_NAME", "mcp-facturas-bucket")
storage_client = storage.Client()
bucket = storage_client.bucket(BUCKET_NAME)

def download_pdf_to_tempfile(source_blob_name):
    # bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(source_blob_name)

    # Crear un archivo temporal
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    blob.download_to_filename(temp_file.name)

    print(f"Archivo temporal descargado en: {temp_file.name}")
    return temp_file.name

def download_pdf_to_tempfile_local(source_path):
    """
    Si el argumento es una ruta local, simplemente copia el archivo PDF
    a un archivo temporal y devuelve su ruta.
    """
    if os.path.exists(source_path):
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        shutil.copy(source_path, temp_file.name)
        print(f"✅ Archivo local copiado a temporal: {temp_file.name}")
        return temp_file.name
    else:
        raise FileNotFoundError(f"No se encontró el archivo local: {source_path}")

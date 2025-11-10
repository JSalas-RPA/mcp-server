import tempfile
from google.cloud import storage
import shutil
import os
import time
import base64
import re
import requests
import numpy as np
from datetime import timedelta

# from src.utilities.config import load_config
# # from src.preprocessing_images import extract_signature, clean_signature, analizar_documento_google, generateScore

# config = load_config("config.yaml")

# TWILIO_ACCOUNT_SID = config['twilio']['account_sid']
# TWILIO_AUTH_TOKEN = config['twilio']['auth_token']

# # Configurar cliente de GCS
BUCKET_NAME = os.getenv("BUCKET_NAME", "mcp-facturas-bucket")
storage_client = storage.Client()
bucket = storage_client.bucket(BUCKET_NAME)
EASYCONTACT_KEY ="3HEfwgZ9EQoRLJrkmCtUf4rY"
ENVIRONMENT = "3HEfwgZ9EQoRLJrkmCtUf4rY"

def upload_image_to_gcs(user_id, image_url):
    print(f'Media URL: {image_url}')
    
    try:
        if ENVIRONMENT == EASYCONTACT_KEY:
            r = requests.get(image_url, verify=False)
        else:
            r = requests.get(image_url, auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN))
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"Error al descargar la imagen: {e}")
        return None

    content_type = r.headers.get("Content-Type", "")
    print(f"Content-Type: {content_type}")

    # if content_type not in ["image/jpeg", "image/png", "image/gif", "pdf"]:
    #     print("Formato de imagen no soportado.")
    #     return None

    image_data = r.content
    image_extension = content_type.split("/")[-1]

    # if ENVIRONMENT != EASYCONTACT_KEY:
    image_name = f"{user_id}/{content_type.split('/')[0]}_{int(time.time())}.{image_extension}"
    
    try:
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(image_name)
        blob.upload_from_string(image_data, content_type=content_type)

        print(f"{content_type.split('/')[0]} subida a gs://{BUCKET_NAME}/{image_name}")
        return image_name
    except Exception as e:
        print(f"Error al subir la imagen a GCS: {e}")
        return None
    

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
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(file_name)
        blob.upload_from_string(file_data, content_type=content_type)
        blob.make_public()  # para obtener URL pública

        print(f"{content_type.split('/')[0]} subida a gs://{BUCKET_NAME}/{file_name}")
        return file_name
    except Exception as e:
        print(f"Error al subir archivo a GCS: {e}")
        return None

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

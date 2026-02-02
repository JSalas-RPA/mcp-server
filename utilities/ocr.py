# utilities/ocr.py
# ============================================
# Funciones de OCR (Optical Character Recognition)
# ============================================
# Contiene las funciones para extraer texto de PDFs e imágenes
# usando diferentes motores: Google Cloud Vision, LlamaParse, PyMuPDF
# ============================================

import os
import io
import tempfile

import fitz  # PyMuPDF
from pdf2image import convert_from_path
from google.cloud import vision_v1
from llama_parse import LlamaParse

# -----------------------------
# Configuración de credenciales GCP
# -----------------------------
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

gcp_key_json = os.getenv("datecKeyCredentials")

if not gcp_key_json:
    raise EnvironmentError("No se encontró la variable de entorno 'datecKeyCredentials'")

# Crear archivo temporal para Google Cloud SDK
with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json") as temp_file:
    temp_file.write(gcp_key_json)
    temp_file.flush()
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = temp_file.name

# -----------------------------
# LlamaParse configuration
# -----------------------------
llama_api_key = os.getenv("LLAMAPARSE_API_KEY")


# ============================================
# FUNCIONES DE OCR
# ============================================

def get_transcript_document(path_doc: str) -> str:
    """
    Extrae texto de un documento usando LlamaParse (OCR premium).

    Args:
        path_doc: Ruta al documento PDF

    Returns:
        Texto extraído del documento
    """
    parser_ci = LlamaParse(
        api_key=llama_api_key,
        result_type="markdown",
        premium_mode=True
    )
    documents = parser_ci.load_data(path_doc)
    text = ""
    for doc in documents:
        text += f"\n {doc.text} \n"
    print("Texto extraído con LlamaParse Document OCR:", text)
    return text


def get_transcript_document_cloud_vision(path_doc: str) -> str:
    """
    Extrae texto de un documento PDF usando Google Cloud Vision OCR.
    Convierte cada página a imagen y aplica OCR.

    Args:
        path_doc: Ruta al documento PDF

    Returns:
        Texto extraído del documento
    """
    client = vision_v1.ImageAnnotatorClient()

    pages = convert_from_path(path_doc)
    full_text = ""

    for page_image in pages:
        buffered = io.BytesIO()
        page_image.save(buffered, format="JPEG")
        content = buffered.getvalue()

        image = vision_v1.Image(content=content)
        response = client.document_text_detection(image=image)

        if response.error.message:
            raise Exception(f"Error: {response.error.message}")

        full_text += response.full_text_annotation.text + "\n"

    return full_text.strip()


def extract_text_from_first_page(file_path: str) -> str:
    """
    Extrae texto de la primera página del PDF usando PyMuPDF.
    Útil para PDFs que ya contienen texto (no escaneados).

    Args:
        file_path: Ruta al archivo PDF

    Returns:
        Texto extraído o código de error si el PDF es escaneado
    """
    try:
        doc = fitz.open(file_path)
        if len(doc) == 0:
            return ""

        # Extraemos solo la primera página
        page = doc[0]
        text_content = page.get_text().strip()

        # Si el texto es casi nulo, asumimos que es imagen (necesitará OCR)
        if len(text_content) < 50:
            return "ERROR:_PDF_SIN_TEXTO_O_ESCANEADO"

        return text_content
    except Exception as e:
        return f"ERROR_PROCESAMIENTO: {str(e)}"

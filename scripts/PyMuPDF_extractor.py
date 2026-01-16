import fitz  # PyMuPDF
import openai
import json

def extract_text_from_first_page(file_path: str) -> str:
    """Extrae texto de la primera página del PDF."""
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

        print("Texto extraído de la primera página:", text_content)
        return text_content
    except Exception as e:
        return f"ERROR_PROCESAMIENTO: {str(e)}"

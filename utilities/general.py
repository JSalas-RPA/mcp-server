import re, os, io
from openai import OpenAI
from llama_parse import LlamaParse
from pdf2image import convert_from_path
from google.cloud import vision_v1
from PIL import Image


os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "datec-d4g-adn-a.json"

openai_client = OpenAI(api_key=os.getenv("API_OPENAI_KEY"))


parser = LlamaParse(api_key= "llx-pca1DxoBCQgCHz2zbfiQIS5ng5P6liwDRIwyb807m4hzODyi",
                    result_type="text",
                    premium_mode=True)

def get_transcript_document(path_doc):
    parser_ci = LlamaParse(api_key= "llx-pca1DxoBCQgCHz2zbfiQIS5ng5P6liwDRIwyb807m4hzODyi", result_type="markdown", premium_mode=True)
    documents = parser_ci.load_data(path_doc)
    text = ""
    for doc in documents:
        text += f"\n {doc.text} \n"
    return text

def get_transcript_document_cloud_vision(path_doc):
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


def get_openai_answer(system_prompt, user_prompt):
    respuesta = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
    )
    return respuesta.choices[0].message.content.strip()

def get_clean_json(text):
    return re.search(r'(\{.*\})', text, re.DOTALL).group(1)
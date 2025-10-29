import json
from utilities.image_storage import download_pdf_to_tempfile
from utilities.general import (
    get_transcript_document_cloud_vision,
    get_openai_answer,
    get_clean_json
)
from prompts import get_invoice_validator_prompt


def validar_factura_tool(rutas_bucket: list[str]) -> dict:
    """
    Tool que valida o extrae información de una factura.
    No usa Redis ni Celery, y no envía mensajes externos.
    Devuelve toda la información directamente.
    """

    try:
        print("🚀 Iniciando validación de factura...")
        resultado_factura = {}

        for image in rutas_bucket:
            print(f"📄 Procesando factura: {image}")
            ruta_temp = download_pdf_to_tempfile(image)
            print(f"📂 Archivo temporal: {ruta_temp}")

            # OCR
            print("👁️  Extrayendo texto con Cloud Vision...")
            text_factura = get_transcript_document_cloud_vision(ruta_temp)
            print(f"📝 Texto extraído (primeros 500 caracteres):\n{text_factura[:2000]}...\n")

            # Prompt para el modelo
            print("🧠 Generando prompt para OpenAI...")
            system_prompt, user_prompt = get_invoice_validator_prompt(text_factura)

            # Llamada al modelo
            print("💬 Enviando a OpenAI para validación de factura...")
            raw_result = get_openai_answer(system_prompt, user_prompt)

            # Limpiar JSON devuelto
            print("🧹 Procesando resultado JSON...")
            resultado_factura = json.loads(get_clean_json(raw_result))

        # Extraer campos
        empresa_emisora = resultado_factura.get("empresa_emisora", "No detectada")
        nit_factura = resultado_factura.get("nit_factura", "No detectado")
        numero_factura = resultado_factura.get("numero_factura", "No detectado")
        codigo_autorizacion = resultado_factura.get("codigo_autorizacion", "No detectado")
        razon_social_cliente = resultado_factura.get("razon_social_cliente", "No detectada")
        nit_ci_ce_cliente = resultado_factura.get("nit_ci_ce_cliente", "No detectado")
        codigo_cliente = resultado_factura.get("codigo_cliente", "No detectado")
        fecha_emision = resultado_factura.get("fecha_emision", "No detectada")
        direccion = resultado_factura.get("direccion", "No detectada")
        ciudad = resultado_factura.get("ciudad", "No detectada")
        subtotal = resultado_factura.get("subtotal", "No detectado")
        monto_total = resultado_factura.get("monto_total", "No detectado")
        productos = resultado_factura.get("productos", [])
        factura_valida = resultado_factura.get("factura_valida", False)
        vigente = resultado_factura.get("vigente", False)

        # Mensaje descriptivo
        if not factura_valida:
            mensaje = "⚠️ La factura no parece válida o tiene inconsistencias. Revisa que esté completa y legible."
        else:
            mensaje = (
                f"✅ Factura validada correctamente.\n"
                f"- Empresa emisora: {empresa_emisora}\n"
                f"- NIT de la factura: {nit_factura}\n"
                f"- Nº Factura: {numero_factura}\n"
                f"- Código de autorización: {codigo_autorizacion}\n"
                f"- Cliente (Razón social): {razon_social_cliente}\n"
                f"- NIT/CI/CE cliente: {nit_ci_ce_cliente}\n"
                f"- Código cliente: {codigo_cliente}\n"
                f"- Fecha de emisión: {fecha_emision}\n"
                f"- Dirección: {direccion}\n"
                f"- Ciudad: {ciudad}\n"
                f"- Subtotal: {subtotal}\n"
                f"- Total: {monto_total}\n"
                f"- Vigente: {'Sí' if vigente else 'No'}\n"
                f"- Productos:\n"
            )

            for p in productos:
                mensaje += f"    • {p.get('producto', 'N/D')} | Cantidad: {p.get('cantidad', 'N/D')} | Unitario: {p.get('precio_unitario', 'N/D')} | Subtotal: {p.get('subtotal', 'N/D')}\n"

        print("✅ Validación de factura completada.")
        return {
            "status": "success",
            "mensaje": mensaje,
            "datos": {
                "empresa_emisora": empresa_emisora,
                "nit_factura": nit_factura,
                "numero_factura": numero_factura,
                "codigo_autorizacion": codigo_autorizacion,
                "razon_social_cliente": razon_social_cliente,
                "nit_ci_ce_cliente": nit_ci_ce_cliente,
                "codigo_cliente": codigo_cliente,
                "fecha_emision": fecha_emision,
                "direccion": direccion,
                "ciudad": ciudad,
                "subtotal": subtotal,
                "monto_total": monto_total,
                "productos": productos,
                "factura_valida": factura_valida,
                "vigente": vigente
            }
        }
    except Exception as e:
        error_msg = f"💥 Error al validar la factura: {str(e)}"
        print(error_msg)
        return {"status": "error", "error": str(e)}




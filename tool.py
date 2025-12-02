# tool.py - Módulo de herramientas para procesamiento de facturas SAP

import json
import logging
import requests
from datetime import datetime
from requests.auth import HTTPBasicAuth
from utilities.general import get_openai_answer, get_clean_json
from utilities.image_storage import download_pdf_to_tempfile
from utilities.general import get_transcript_document_cloud_vision
from prompts import get_invoice_validator_prompt, get_invoice_text_parser_prompt

# Configuración de logging para Google Cloud Run
logger = logging.getLogger(__name__)

# Configuración de endpoints SAP desde variables de entorno
SAP_CONFIG = {
    'username': "BOT_ASSET_CHANGES",
    'password': "FJyB@~[NkeSenF5WiMj>7=w+>fuFB~R[xDqjcEni",
    'supplier_url': "https://my408830-api.s4hana.cloud.sap/sap/opu/odata/sap/API_BUSINESS_PARTNER/A_Supplier",
    'purchase_order_url': "https://my408830-api.s4hana.cloud.sap/sap/opu/odata/sap/API_PURCHASEORDER/A_PurchaseOrder",
    'invoice_post_url': "https://my408830-api.s4hana.cloud.sap/sap/opu/odata/sap/API_SUPPLIERINVOICE_PROCESS_SRV/A_SupplierInvoice"
}


# ============================================================================
# FUNCIONES AUXILIARES
# ============================================================================

def safe_json_response(response):
    """Valida que la respuesta HTTP contenga JSON y maneja errores."""
    try:
        return response.json()
    except json.JSONDecodeError:
        logger.error(f"Respuesta no es JSON válido. Status: {response.status_code}")
        logger.error(f"Contenido: {response.text[:500]}")
        return None
    except Exception as e:
        logger.error(f"Excepción al parsear respuesta JSON: {str(e)}")
        return None


def format_sap_date(date_str):
    """Convierte cualquier formato de fecha al requerido por SAP (YYYY-MM-DDT00:00:00)."""
    if not date_str:
        return None
    
    date_part = date_str.split("T")[0] if "T" in date_str else date_str
    
    date_formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
    ]
    
    for fmt in date_formats:
        try:
            dt = datetime.strptime(date_part, fmt)
            return dt.strftime("%Y-%m-%dT00:00:00")
        except ValueError:
            continue
    
    logger.warning(f"No se pudo parsear la fecha: {date_str}. Usando fecha actual.")
    return datetime.now().strftime("%Y-%m-%dT00:00:00")


def obtener_sesion_con_token():
    """Obtiene una sesión con token CSRF válido para SAP."""
    session = requests.Session()
    session.auth = HTTPBasicAuth(SAP_CONFIG['username'], SAP_CONFIG['password'])
    
    try:
        headers_get = {
            "Accept": "application/json",
            "x-csrf-token": "Fetch"
        }
        
        logger.info("Obteniendo token CSRF de SAP")
        response = session.get(
            SAP_CONFIG['invoice_post_url'],
            headers=headers_get,
            timeout=30
        )
        
        if response.status_code != 200:
            logger.error(f"Error al obtener token CSRF: {response.status_code}")
            return None, None
        
        token = response.headers.get("x-csrf-token")
        if not token:
            logger.error("No se encontró x-csrf-token en los headers de SAP")
            return None, None
        
        logger.info("Token CSRF obtenido exitosamente")
        return session, token
        
    except Exception as e:
        logger.error(f"Error al obtener sesión con token: {e}")
        return None, None


# ============================================================================
# FUNCIONES PRINCIPALES DE SAP
# ============================================================================

def extraer_datos_factura_desde_texto(texto_factura):
    """Extrae datos principales de la factura desde texto OCR usando OpenAI."""
    try:
        system_prompt, user_prompt = get_invoice_text_parser_prompt(texto_factura)
        raw_result = get_openai_answer(system_prompt, user_prompt)
        
        # Limpiar y parsear respuesta
        raw_result = get_clean_json(raw_result)
        datos = json.loads(raw_result)
        
        # Validar y corregir formato de campos críticos
        if "DocumentDate" in datos:
            datos["DocumentDate"] = format_sap_date(datos["DocumentDate"])
        
        if "InvoiceGrossAmount" in datos:
            try:
                datos["InvoiceGrossAmount"] = float(datos["InvoiceGrossAmount"])
            except (ValueError, TypeError):
                logger.error(f"Formato de monto inválido: {datos['InvoiceGrossAmount']}")
                datos["InvoiceGrossAmount"] = 0.0
        
        logger.info("Datos de factura extraídos exitosamente")
        return datos
        
    except json.JSONDecodeError as e:
        logger.error(f"Error al parsear respuesta de OpenAI: {e}")
        raise
    except Exception as e:
        logger.error(f"Error en extracción de datos de factura: {e}")
        raise


def obtener_proveedores_sap():
    """Obtiene todos los proveedores desde SAP API."""
    try:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        response = requests.get(
            SAP_CONFIG['supplier_url'],
            headers=headers,
            auth=HTTPBasicAuth(SAP_CONFIG['username'], SAP_CONFIG['password']),
            timeout=30
        )
        
        if response.status_code == 200:
            data = safe_json_response(response)
            if data:
                proveedores = data.get("d", {}).get("results", [])
                logger.info(f"{len(proveedores)} proveedores obtenidos de SAP")
                return proveedores
        else:
            logger.error(f"Error {response.status_code} al obtener proveedores de SAP")
            
    except Exception as e:
        logger.error(f"Excepción en obtener_proveedores_sap: {e}")
    
    return []


def buscar_proveedor_en_sap(factura_datos, proveedores_sap):
    """Busca y valida el proveedor en la lista de proveedores de SAP."""
    tax_buscar = str(factura_datos.get("SupplierTaxNumber", "")).strip()
    nombre_buscar = factura_datos.get("SupplierName", "").upper().strip()
    
    logger.info(f"Buscando proveedor en SAP: '{nombre_buscar}' (Tax: {tax_buscar})")
    
    # Búsqueda exacta por tax number
    if tax_buscar:
        for proveedor in proveedores_sap:
            if str(proveedor.get("TaxNumber1", "")).strip() == tax_buscar:
                logger.info(f"Proveedor encontrado por tax number exacto: {tax_buscar}")
                return {
                    "Supplier": proveedor.get("Supplier"),
                    "SupplierFullName": proveedor.get("SupplierFullName"),
                    "SupplierName": proveedor.get("SupplierName"),
                    "SupplierAccountGroup": proveedor.get("SupplierAccountGroup"),
                    "TaxNumber": proveedor.get("TaxNumber1")
                }
    
    # Búsqueda por nombre aproximado
    for proveedor in proveedores_sap:
        nombre_proveedor = proveedor.get("SupplierName", "").upper()
        nombre_completo = proveedor.get("SupplierFullName", "").upper()
        
        def limpiar_nombre(n):
            return (n.replace("S.A.", "")
                     .replace("S.R.L.", "")
                     .replace("LTDA", "")
                     .replace("LTDA.", "")
                     .replace(".", "")
                     .replace(",", "")
                     .strip())
        
        nombre_buscar_limpio = limpiar_nombre(nombre_buscar)
        nombre_proveedor_limpio = limpiar_nombre(nombre_proveedor)
        nombre_completo_limpio = limpiar_nombre(nombre_completo)
        
        if (nombre_buscar_limpio in nombre_proveedor_limpio or 
            nombre_buscar_limpio in nombre_completo_limpio or
            nombre_proveedor_limpio in nombre_buscar_limpio):
            
            logger.info(f"Proveedor encontrado por nombre aproximado: {nombre_proveedor}")
            return {
                "Supplier": proveedor.get("Supplier"),
                "SupplierFullName": proveedor.get("SupplierFullName"),
                "SupplierName": proveedor.get("SupplierName"),
                "SupplierAccountGroup": proveedor.get("SupplierAccountGroup"),
                "TaxNumber": proveedor.get("TaxNumber1")
            }
    
    logger.error(f"Proveedor no encontrado para: '{nombre_buscar}' (Tax: {tax_buscar})")
    return None


def obtener_ordenes_compra_proveedor(supplier_code):
    """Obtiene las órdenes de compra activas para un proveedor específico."""
    try:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        url = f"{SAP_CONFIG['purchase_order_url']}?$filter=Supplier eq '{supplier_code}'&$top=10"
        response = requests.get(
            url,
            headers=headers,
            auth=HTTPBasicAuth(SAP_CONFIG['username'], SAP_CONFIG['password']),
            timeout=30
        )
        
        if response.status_code == 200:
            data = safe_json_response(response)
            if data and "d" in data and "results" in data["d"]:
                oc_list = data["d"]["results"]
                if oc_list:
                    logger.info(f"{len(oc_list)} órdenes de compra encontradas para proveedor {supplier_code}")
                    return oc_list
                else:
                    logger.warning(f"No se encontraron órdenes de compra para el proveedor {supplier_code}")
            else:
                logger.warning("No se encontraron datos de órdenes de compra en la respuesta")
        else:
            logger.warning(f"No se pudo acceder a API de órdenes de compra (Status: {response.status_code})")
            
    except Exception as e:
        logger.error(f"Error al obtener órdenes de compra: {e}")
    
    return []


def construir_json_factura_sap(factura_datos, proveedor_info, oc_items):
    """Construye el JSON final en el formato exacto que SAP espera."""
    if not proveedor_info:
        raise ValueError("Información del proveedor no disponible")
    
    fecha_documento = format_sap_date(factura_datos.get("DocumentDate"))
    invoice_id = factura_datos.get("SupplierInvoiceIDByInvcgParty", "")
    
    if not invoice_id or invoice_id == "0":
        logger.warning("No se encontró ID de factura, generando automático")
        invoice_id = f"INV{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    invoice_amount = factura_datos.get("InvoiceGrossAmount", 0.0)
    invoice_amount_str = f"{invoice_amount:.2f}"
    
    # Validar que tenemos OC para continuar
    if not oc_items:
        logger.error("No se encontraron órdenes de compra para esta factura")
        logger.error("La factura NO puede ser procesada sin OC asociada")
        return None
    
    # Estructura base de factura para SAP
    factura_json = {
        "CompanyCode": "1000",
        "DocumentDate": fecha_documento,
        "PostingDate": fecha_documento,
        "SupplierInvoiceIDByInvcgParty": invoice_id,
        "InvoicingParty": proveedor_info.get("Supplier", ""),
        "DocumentCurrency": "BOB",
        "InvoiceGrossAmount": invoice_amount_str,
        "DueCalculationBaseDate": fecha_documento,
        "TaxIsCalculatedAutomatically": True,
        "TaxDeterminationDate": fecha_documento,
        "SupplierInvoiceStatus": "A",
        "to_SuplrInvcItemPurOrdRef": {
            "results": []
        }
    }
    
    # Agregar items basados en las OC encontradas
    for idx, oc in enumerate(oc_items, start=1):
        item = {
            "SupplierInvoiceItem": str(idx).zfill(5),
            "PurchaseOrder": oc.get("PurchaseOrder", ""),
            "PurchaseOrderItem": oc.get("PurchaseOrderItem", "00010"),
            "DocumentCurrency": "BOB",
            "QuantityInPurchaseOrderUnit": "1.000",
            "PurchaseOrderQuantityUnit": "EA",
            "SupplierInvoiceItemAmount": invoice_amount_str,
            "TaxCode": "V0"
        }
        factura_json["to_SuplrInvcItemPurOrdRef"]["results"].append(item)
        logger.info(f"Referenciando OC: {oc.get('PurchaseOrder')}, Item: {oc.get('PurchaseOrderItem')}")
    
    return factura_json


def enviar_factura_a_sap_service(factura_json):
    """Envía la factura a SAP usando token CSRF y sesión persistente."""
    session, token = obtener_sesion_con_token()
    if not session or not token:
        logger.error("No se pudo obtener sesión con token válido para SAP")
        return None
    
    try:
        headers_post = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-csrf-token": token
        }
        
        logger.info("Enviando factura a SAP")
        
        response = session.post(
            SAP_CONFIG['invoice_post_url'],
            headers=headers_post,
            json={"d": factura_json},
            timeout=30
        )
        
        logger.info(f"Respuesta de SAP: Status {response.status_code}")
        
        if response.status_code in [200, 201]:
            logger.info("Factura creada exitosamente en SAP")
            data = safe_json_response(response)
            return data
        else:
            logger.error(f"Error al crear factura en SAP: {response.status_code}")
            logger.error(f"Detalles: {response.text[:500]}")
            return None
            
    except Exception as e:
        logger.error(f"Error en envío a SAP: {e}")
        return None
    finally:
        if session:
            session.close()


# ============================================================================
# FUNCIONES PRINCIPALES PARA MCP SERVER
# ============================================================================

def procesar_factura_completa(texto_factura):
    """
    FUNCIÓN PRINCIPAL - Procesa una factura desde texto OCR hasta carga en SAP.
    
    Retorno:
    - dict con keys: 'success', 'message', 'data', 'error' (si aplica)
    """
    logger.info("INICIANDO PROCESO COMPLETO DE CARGA DE FACTURA")
    
    resultado = {
        'success': False,
        'message': '',
        'data': None,
        'error': None
    }
    
    try:
        # PASO 1: EXTRACCIÓN DE DATOS DE LA FACTURA
        logger.info("1. EXTRACCIÓN DE DATOS DE FACTURA")
        
        factura_datos = extraer_datos_factura_desde_texto(texto_factura)
        
        if not factura_datos:
            error_msg = "No se pudieron extraer datos de la factura"
            logger.error(error_msg)
            resultado['error'] = error_msg
            return resultado
        
        logger.info(f"Datos extraídos - Factura: {factura_datos.get('SupplierInvoiceIDByInvcgParty')}")
        logger.info(f"Proveedor: {factura_datos.get('SupplierName')}")
        logger.info(f"Tax: {factura_datos.get('SupplierTaxNumber')}")
        logger.info(f"Monto: {factura_datos.get('InvoiceGrossAmount', 0):.2f} BOB")
        logger.info(f"Fecha: {factura_datos.get('DocumentDate')}")
        
        # PASO 2: OBTENCIÓN Y VALIDACIÓN DE PROVEEDOR EN SAP
        logger.info("2. VALIDACIÓN DE PROVEEDOR EN SAP")
        
        proveedores_sap = obtener_proveedores_sap()
        if not proveedores_sap:
            error_msg = "No se pudieron obtener proveedores de SAP"
            logger.error(error_msg)
            resultado['error'] = error_msg
            return resultado
        
        proveedor_info = buscar_proveedor_en_sap(factura_datos, proveedores_sap)
        if not proveedor_info:
            error_msg = f"Proveedor no encontrado en SAP: {factura_datos.get('SupplierName')}"
            logger.error(error_msg)
            resultado['error'] = error_msg
            return resultado
        
        logger.info(f"Proveedor validado - Código: {proveedor_info.get('Supplier')}")
        logger.info(f"Nombre: {proveedor_info.get('SupplierName')}")
        
        # PASO 3: OBTENCIÓN DE ÓRDENES DE COMPRA ASOCIADAS
        logger.info("3. BUSQUEDA DE ÓRDENES DE COMPRA")
        
        supplier_code = proveedor_info.get("Supplier", "")
        if not supplier_code:
            error_msg = "Código de proveedor no disponible"
            logger.error(error_msg)
            resultado['error'] = error_msg
            return resultado
        
        oc_items = obtener_ordenes_compra_proveedor(supplier_code)
        
        # CRÍTICO: Validar que tenemos OC para continuar
        if not oc_items:
            error_msg = f"No se encontraron órdenes de compra para el proveedor {supplier_code}"
            logger.error(error_msg)
            logger.error("El proceso se detiene. Esta factura no puede ser cargada sin OC.")
            resultado['error'] = error_msg
            resultado['message'] = "Factura no tiene OC asociada en SAP"
            return resultado
        
        logger.info(f"{len(oc_items)} órdenes de compra encontradas")
        
        # PASO 4: CONSTRUCCIÓN DEL JSON PARA SAP
        logger.info("4. CONSTRUCCIÓN DE JSON PARA SAP")
        
        factura_json = construir_json_factura_sap(factura_datos, proveedor_info, oc_items)
        
        if not factura_json:
            error_msg = "No se pudo construir el JSON para SAP"
            logger.error(error_msg)
            resultado['error'] = error_msg
            return resultado
        
        # PASO 5: ENVÍO A SAP
        logger.info("5. ENVÍO A SAP")
        
        respuesta_sap = enviar_factura_a_sap_service(factura_json)
        
        if not respuesta_sap:
            error_msg = "No se pudo enviar la factura a SAP"
            logger.error(error_msg)
            resultado['error'] = error_msg
            return resultado
        
        # ÉXITO: Factura cargada correctamente
        logger.info("FACTURA CREADA EXITOSAMENTE EN SAP")
        
        resultado['success'] = True
        resultado['message'] = "Factura cargada exitosamente en SAP"
        resultado['data'] = {
            'factura_id': factura_json.get('SupplierInvoiceIDByInvcgParty'),
            'proveedor': proveedor_info.get('SupplierName'),
            'proveedor_codigo': proveedor_info.get('Supplier'),
            'monto': factura_json.get('InvoiceGrossAmount'),
            'oc_count': len(oc_items),
            'respuesta_sap': respuesta_sap
        }
        
        return resultado
        
    except Exception as e:
        error_msg = f"Error inesperado en el procesamiento: {str(e)}"
        logger.error(error_msg)
        
        resultado['error'] = error_msg
        resultado['message'] = "Error en el procesamiento de la factura"
        
        return resultado


def validar_factura_tool(rutas_bucket: list[str]) -> dict:
    """
    Tool que valida o extrae información de una factura.
    No usa Redis ni Celery, y no envía mensajes externos.
    Devuelve toda la información directamente.
    """
    try:
        logger.info("Iniciando validación de factura")
        resultado_factura = {}

        for image in rutas_bucket:
            logger.info(f"Procesando factura: {image}")
            ruta_temp = download_pdf_to_tempfile(image)
            logger.info(f"Archivo temporal: {ruta_temp}")

            # OCR
            logger.info("Extrayendo texto con Cloud Vision")
            text_factura = get_transcript_document_cloud_vision(ruta_temp)
            logger.info(f"Texto extraído (primeros 2000 caracteres):\n{text_factura[:2000]}")

            # Prompt para el modelo
            logger.info("Generando prompt para OpenAI")
            system_prompt, user_prompt = get_invoice_validator_prompt(text_factura)

            # Llamada al modelo
            logger.info("Enviando a OpenAI para validación de factura")
            raw_result = get_openai_answer(system_prompt, user_prompt)

            # Limpiar JSON devuelto
            logger.info("Procesando resultado JSON")
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
            mensaje = "La factura no parece válida o tiene inconsistencias. Revisa que esté completa y legible."
        else:
            mensaje = (
                f"Factura validada correctamente.\n"
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

        logger.info("Validación de factura completada")
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
        error_msg = f"Error al validar la factura: {str(e)}"
        logger.error(error_msg)
        return {"status": "error", "error": str(e)}


def enviar_factura_a_sap_tool(datos_factura: dict, correo_remitente: str) -> dict:
    """
    Envía los datos validados de la factura al sistema SAP S/4HANA.
    
    Parámetros:
        datos_factura: dict con los datos validados de la factura
        correo_remitente: correo que realizó la consulta
    
    Devuelve:
        dict con el resultado de la operación
    """
    try:
        logger.info(f"Tool 'enviar_factura_a_sap' llamada para el correo={correo_remitente}")
        
        # Convertir datos del formato de validación al formato SAP
        texto_factura = f"""
        Factura Nº: {datos_factura.get('numero_factura', '')}
        Proveedor: {datos_factura.get('empresa_emisora', '')}
        NIT: {datos_factura.get('nit_factura', '')}
        Fecha: {datos_factura.get('fecha_emision', '')}
        Monto Total: {datos_factura.get('monto_total', '')}
        """
        
        # Procesar la factura completa
        resultado = procesar_factura_completa(texto_factura)
        
        if resultado['success']:
            return {
                "status": "success",
                "message": f"Factura {resultado['data']['factura_id']} creada exitosamente en SAP",
                "data": resultado['data']
            }
        else:
            return {
                "status": "error",
                "message": resultado['message'],
                "error": resultado['error']
            }
            
    except Exception as e:
        error_msg = f"Error en enviar_factura_a_sap_tool: {str(e)}"
        logger.error(error_msg)
        return {"status": "error", "error": str(e)}
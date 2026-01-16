# ============================================================================
# Server MCP Dsuite
# Author: Jordi Salas
# Date: 2024-06-10
# Description: Procesamiento de facturas con validación avanzada de proveedores en SAP
# ============================================================================
import requests
import os
import json
import logging
import re, dotenv
from datetime import datetime
from difflib import SequenceMatcher
from requests.auth import HTTPBasicAuth
from utilities.prompts import get_OC_validator_prompt, get_invoice_text_parser_prompt, get_invoice_validator_prompt
from utilities.general import get_openai_answer, get_transcript_document_cloud_vision
from utilities.image_storage import download_pdf_to_tempfile

# ============================================================================
# CONFIGURACIÓN Y LOGGING
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('factura_process.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Intentar cargar .env si python-dotenv está instalado
try:
    from dotenv import load_dotenv
    load_dotenv()  # carga variables desde .env al entorno
except Exception:
    pass

# Configuración de endpoints SAP - CORREGIDO
SAP_CONFIG = {
    'username': os.getenv('SAP_USERNAME', ''),
    'password': os.getenv('SAP_PASSWORD', ''),
    'supplier_url': os.getenv('SAP_SUPPLIER_URL', 'https://my408830-api.s4hana.cloud.sap/sap/opu/odata/sap/API_BUSINESS_PARTNER/A_Supplier'),
    'purchase_order_url': os.getenv('SAP_PURCHASE_ORDER_URL', 'https://my408830-api.s4hana.cloud.sap/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV/A_PurchaseOrder'),
    'invoice_post_url': os.getenv('SAP_INVOICE_POST_URL', 'https://my408830-api.s4hana.cloud.sap/sap/opu/odata/sap/API_SUPPLIERINVOICE_PROCESS_SRV/A_SupplierInvoice'),
    'material_doc_url': os.getenv('SAP_MATERIAL_DOC_URL', 'https://my408830-api.s4hana.cloud.sap/sap/opu/odata/sap/API_GOODS_MOVEMENT_SRV/A_MaterialDocument')
}

# ============================================================================
# FUNCIONES DE UTILIDAD MEJORADAS
# ============================================================================

def calcular_similitud_nombres(nombre1, nombre2):
    """
    Calcula la similitud entre dos nombres usando SequenceMatcher.
    Retorna un valor entre 0 y 1.
    """
    return SequenceMatcher(None, nombre1.lower(), nombre2.lower()).ratio()

def limpiar_nombre_minimo(nombre):
    """
    Limpieza mínima: solo espacios extra, símbolos y normalización.
    NO elimina SRL, LTDA, Laboratorios, etc.
    """
    if not nombre:
        return ""
    
    # Convertir a mayúsculas y quitar espacios extras
    nombre = nombre.upper().strip()
    
    # Remover solo símbolos innecesarios pero mantener palabras
    nombre = re.sub(r'[^\w\s\.\-]', ' ', nombre)
    nombre = re.sub(r'\s+', ' ', nombre).strip()
    
    return nombre

def extraer_solo_numeros(texto):
    """
    Extrae solo los números de un texto.
    """
    if not texto:
        return ""
    return re.sub(r'\D', '', texto)

def safe_json_response(response):
    """
    Valida que la respuesta HTTP contenga JSON y maneja errores.
    """
    try:
        return response.json()
    except json.JSONDecodeError:
        logger.error(f"Respuesta no es JSON válido. Status: {response.status_code}")
        logger.error(f"Contenido: {response.text[:500]}")
        return None
    except Exception as e:
        logger.error(f"Excepción al parsear respuesta JSON: {str(e)}")
        return None

def clean_openai_json(raw_result):
    """
    Limpia el texto devuelto por OpenAI para que sea JSON válido.
    """
    if not raw_result:
        raise ValueError("Respuesta vacía de OpenAI")
    
    raw_result = raw_result.strip()
    
    if raw_result.startswith("```json"):
        raw_result = raw_result.replace("```json", "").strip()
    elif raw_result.startswith("```"):
        raw_result = raw_result.replace("```", "").strip()
    
    raw_result = raw_result.rstrip("`").strip()
    return raw_result

def format_sap_date(date_str):
    """
    Convierte cualquier formato de fecha al formato requerido por SAP (YYYY-MM-DDT00:00:00).
    """
    if not date_str:
        return None
    
    if "T00:00:00" in date_str and len(date_str.split("T")[0]) == 10:
        return date_str
    
    date_part = date_str.split("T")[0] if "T" in date_str else date_str
    
    date_formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d/%m/%Y %H:%M",
        "%m/%d/%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
    ]
    
    for fmt in date_formats:
        try:
            dt = datetime.strptime(date_part.strip(), fmt)
            return dt.strftime("%Y-%m-%dT00:00:00")
        except ValueError:
            continue
    
    logger.warning(f"No se pudo parsear la fecha: {date_str}. Usando fecha actual.")
    return datetime.now().strftime("%Y-%m-%dT00:00:00")

def obtener_sesion_con_token():
    """
    Obtiene una sesión con token CSRF válido para SAP.
    """
    session = requests.Session()
    session.auth = HTTPBasicAuth(SAP_CONFIG['username'], SAP_CONFIG['password'])
    
    try:
        headers_get = {
            "Accept": "application/json",
            "x-csrf-token": "Fetch"
        }
        
        logger.info("Obteniendo token CSRF de SAP...")
        response = session.get(
            SAP_CONFIG['invoice_post_url'],
            headers=headers_get,
            timeout=30
        )
        
        if response.status_code != 200:
            logger.error(f"Error al obtener token CSRF: {response.status_code}")
            logger.error(f"Respuesta: {response.text[:200]}")
            return None, None
        
        token = response.headers.get("x-csrf-token")
        if not token:
            logger.error("No se encontró x-csrf-token en los headers de SAP")
            return None, None
        
        logger.info("✓ Token CSRF obtenido exitosamente")
        return session, token
        
    except Exception as e:
        logger.error(f"Error al obtener sesión con token: {e}")
        return None, None

# ============================================================================
# FUNCIONES PRINCIPALES DE EXTRACCIÓN Y VALIDACIÓN MEJORADAS
# ============================================================================

def extraer_datos_factura_desde_texto(texto_factura):
    """
    Extrae datos principales de la factura desde texto OCR usando OpenAI.
    """
    try:
        system_prompt, user_prompt = get_invoice_text_parser_prompt(texto_factura)
        
        logger.info("📝 Llamando a OpenAI para extraer datos de factura...")
        raw_result = get_openai_answer(system_prompt, user_prompt)
        
        raw_result = clean_openai_json(raw_result)
        datos = json.loads(raw_result)
        
        print("\n" + "="*70)
        print("📋 DATOS EXTRAÍDOS DE LA FACTURA (OpenAI):")
        print("="*70)
        for key, value in datos.items():
            print(f"  {key}: {value}")
        print("="*70)
        
        datos_transformados = datos.copy()
            # Validar campos requeridos
        campos_requeridos = ["SupplierName", "SupplierInvoiceIDByInvcgParty", "InvoiceGrossAmount", "DocumentDate","Description"]
        for campo in campos_requeridos:
            if campo not in datos_transformados:
                logger.warning(f"Campo requerido '{campo}' no encontrado en datos extraídos")
        
        if "SupplierTaxNumber" in datos_transformados and datos_transformados["SupplierTaxNumber"]:
            datos_transformados["SupplierTaxNumber"] = extraer_solo_numeros(str(datos_transformados["SupplierTaxNumber"]))
        
        if "DocumentDate" in datos_transformados:
            datos_transformados["DocumentDate"] = format_sap_date(datos_transformados["DocumentDate"])
        
        if "InvoiceGrossAmount" in datos_transformados:
            try:
                monto_str = str(datos_transformados["InvoiceGrossAmount"])
                monto_str = monto_str.replace(',', '').replace('Bs', '').replace('$', '').replace('BOB', '').strip()
                datos_transformados["InvoiceGrossAmount"] = float(monto_str)
            except (ValueError, TypeError) as e:
                logger.error(f"Formato de monto inválido: {datos_transformados['InvoiceGrossAmount']} - Error: {e}")
                datos_transformados["InvoiceGrossAmount"] = 0.0
        
        logger.info("✓ Datos de factura extraídos y transformados exitosamente")
        return datos_transformados
        
    except json.JSONDecodeError as e:
        logger.error(f"Error al parsear respuesta de OpenAI: {e}")
        raise
    except Exception as e:
        logger.error(f"Error en extracción de datos de factura: {e}")
        raise

def obtener_proveedores_sap():
    """
    Obtiene todos los proveedores desde SAP API.
    """
    try:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        logger.info("🔍 Obteniendo lista de proveedores desde SAP...")
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
                logger.info(f"✓ {len(proveedores)} proveedores obtenidos de SAP")
                
                print("\n" + "="*70)
                print("📋 PROVEEDORES OBTENIDOS DE SAP (primeros 10):")
                print("="*70)
                for i, proveedor in enumerate(proveedores[:10]):
                    supplier_name = proveedor.get('SupplierName') or proveedor.get('BusinessPartnerName') or "N/A"
                    supplier_code = proveedor.get('Supplier') or proveedor.get('BusinessPartner') or "N/A"
                    tax_number = proveedor.get('TaxNumber1') or proveedor.get('TaxNumber') or "N/A"
                    
                    print(f"  {i+1:2d}. {supplier_name[:40]:40} | Código: {supplier_code:10} | Tax: {tax_number}")
                if len(proveedores) > 10:
                    print(f"  ... y {len(proveedores) - 10} más")
                print("="*70)
                
                return proveedores
        else:
            logger.error(f"Error {response.status_code} al obtener proveedores de SAP")
            print(f"\n❌ Error al obtener proveedores: Status {response.status_code}")
            print(f"   Respuesta: {response.text[:200]}")
            
    except Exception as e:
        logger.error(f"Excepción en obtener_proveedores_sap: {e}")
    
    return []

def buscar_proveedor_en_sap(factura_datos, proveedores_sap):
    """
    Busca y valida el proveedor en la lista de proveedores de SAP.
    MEJORADA: Estrategia de búsqueda múltiple robusta.
    """
    tax_buscar = str(factura_datos.get("SupplierTaxNumber", "")).strip()
    nombre_buscar_original = factura_datos.get("SupplierName", "").strip()
    nombre_buscar = limpiar_nombre_minimo(nombre_buscar_original)
    
    print("\n" + "="*70)
    print("🔍 BUSCANDO PROVEEDOR EN SAP:")
    print("="*70)
    print(f"  Nombre original: {nombre_buscar_original}")
    print(f"  Nombre limpio: {nombre_buscar}")
    print(f"  Tax Number: {tax_buscar}")
    print("="*70)
    
    logger.info(f"Buscando proveedor en SAP: '{nombre_buscar_original}' (Tax: {tax_buscar})")
    
    resultados = []
    metodo_usado = ""
    
    # ESTRATEGIA 1: Búsqueda exacta por Tax Number (MÁS CONFIABLE)
    if tax_buscar and tax_buscar != "":
        print(f"  🔍 ESTRATEGIA 1: Búsqueda exacta por Tax Number")
        for proveedor in proveedores_sap:
            tax_campos = ['TaxNumber1', 'TaxNumber', 'SupplierTaxNumber']
            tax_proveedor = ""
            
            for campo in tax_campos:
                if campo in proveedor and proveedor[campo]:
                    tax_proveedor = extraer_solo_numeros(str(proveedor[campo]))
                    break
            
            if tax_proveedor and tax_proveedor == tax_buscar:
                print(f"    ✅ ENCONTRADO: Tax {tax_buscar} coincide exactamente")
                
                supplier_name = proveedor.get('SupplierName') or proveedor.get('BusinessPartnerName') or "N/A"
                supplier_code = proveedor.get('Supplier') or proveedor.get('BusinessPartner') or "N/A"
                supplier_full = proveedor.get('SupplierFullName') or proveedor.get('BusinessPartnerFullName') or supplier_name
                
                resultados.append({
                    "Supplier": supplier_code,
                    "SupplierFullName": supplier_full,
                    "SupplierName": supplier_name,
                    "SupplierAccountGroup": proveedor.get('SupplierAccountGroup') or proveedor.get('BusinessPartnerGrouping') or "N/A",
                    "TaxNumber": tax_proveedor,
                    "Similitud": 1.0,
                    "Metodo": "Tax Number Exacto"
                })
                metodo_usado = "Tax Number Exacto"
                break
    
    # ESTRATEGIA 2: Búsqueda por similitud de nombres COMPLETOS (sin limpiar mucho)
    if not resultados:
        print(f"  🔍 ESTRATEGIA 2: Búsqueda por similitud de nombres completos")
        for proveedor in proveedores_sap:
            supplier_name = proveedor.get('SupplierName') or proveedor.get('BusinessPartnerName') or ""
            supplier_full = proveedor.get('SupplierFullName') or proveedor.get('BusinessPartnerFullName') or supplier_name
            
            # Limpiar mínimamente para comparación
            supplier_name_limpio = limpiar_nombre_minimo(supplier_name)
            supplier_full_limpio = limpiar_nombre_minimo(supplier_full)
            
            # Calcular similitud con ambos nombres
            similitud_name = calcular_similitud_nombres(nombre_buscar, supplier_name_limpio)
            similitud_full = calcular_similitud_nombres(nombre_buscar, supplier_full_limpio)
            
            # Usar la mayor similitud
            similitud = max(similitud_name, similitud_full)
            
            if similitud >= 0.6:  # Umbral más bajo para capturar más posibilidades
                resultados.append({
                    "Supplier": proveedor.get('Supplier') or proveedor.get('BusinessPartner') or "N/A",
                    "SupplierFullName": supplier_full,
                    "SupplierName": supplier_name,
                    "SupplierAccountGroup": proveedor.get('SupplierAccountGroup') or proveedor.get('BusinessPartnerGrouping') or "N/A",
                    "TaxNumber": extraer_solo_numeros(str(proveedor.get('TaxNumber1') or proveedor.get('TaxNumber') or "")),
                    "Similitud": similitud,
                    "Metodo": f"Similitud de Nombres ({similitud*100:.1f}%)"
                }) 
    
    # ESTRATEGIA 3: Búsqueda por palabras clave
    if not resultados and nombre_buscar:
        print(f"  🔍 ESTRATEGIA 3: Búsqueda por palabras clave")
        palabras_clave = nombre_buscar.split()
        for proveedor in proveedores_sap:
            supplier_name = proveedor.get('SupplierName') or proveedor.get('BusinessPartnerName') or ""
            supplier_full = proveedor.get('SupplierFullName') or proveedor.get('BusinessPartnerFullName') or supplier_name
            
            nombre_combinado = f"{supplier_name} {supplier_full}".upper()
            coincidencias = 0
            
            for palabra in palabras_clave:
                if palabra and palabra in nombre_combinado:
                    coincidencias += 1
            
            if coincidencias >= max(1, len(palabras_clave) * 0.5):  # Al menos 50% de coincidencia
                similitud = coincidencias / len(palabras_clave) if palabras_clave else 0
                resultados.append({
                    "Supplier": proveedor.get('Supplier') or proveedor.get('BusinessPartner') or "N/A",
                    "SupplierFullName": supplier_full,
                    "SupplierName": supplier_name,
                    "SupplierAccountGroup": proveedor.get('SupplierAccountGroup') or proveedor.get('BusinessPartnerGrouping') or "N/A",
                    "TaxNumber": extraer_solo_numeros(str(proveedor.get('TaxNumber1') or proveedor.get('TaxNumber') or "")),
                    "Similitud": similitud,
                    "Metodo": f"Coincidencia de Palabras ({coincidencias}/{len(palabras_clave)})"
                })
    
    # Seleccionar el mejor resultado
    if resultados:
        # Ordenar por similitud descendente
        resultados.sort(key=lambda x: x["Similitud"], reverse=True)
        mejor_resultado = resultados[0]
        
        print(f"  ✅ PROVEEDOR ENCONTRADO:")
        print(f"     • Método: {mejor_resultado['Metodo']}")
        print(f"     • Nombre: {mejor_resultado['SupplierName']}")
        print(f"     • Código SAP: {mejor_resultado['Supplier']}")
        print(f"     • Tax: {mejor_resultado['TaxNumber']}")
        print(f"     • Similitud: {mejor_resultado['Similitud']*100:.1f}%")
        
        # Advertencia si el tax number no coincide
        if tax_buscar and mejor_resultado['TaxNumber'] and tax_buscar != mejor_resultado['TaxNumber']:
            print(f"  ⚠️  ADVERTENCIA: Tax number no coincide (Factura: {tax_buscar}, SAP: {mejor_resultado['TaxNumber']})")
            logger.warning(f"Tax number no coincide: factura={tax_buscar}, SAP={mejor_resultado['TaxNumber']}")
        
        logger.info(f"✓ Proveedor encontrado por {mejor_resultado['Metodo']}: {mejor_resultado['SupplierName']}")
        
        # Retornar sin el campo de similitud y método
        return {
            "Supplier": mejor_resultado["Supplier"],
            "SupplierFullName": mejor_resultado["SupplierFullName"],
            "SupplierName": mejor_resultado["SupplierName"],
            "SupplierAccountGroup": mejor_resultado["SupplierAccountGroup"],
            "TaxNumber": mejor_resultado["TaxNumber"],
            "MetodoBusqueda": mejor_resultado["Metodo"],
            "Similitud": mejor_resultado["Similitud"]
        }
    
    # ESTRATEGIA 4: Usar AI si todo falla
    print("  🔍 ESTRATEGIA 4: Usando AI para validación (métodos anteriores fallaron)")
    logger.warning("Proveedor no encontrado por búsqueda directa. Usando AI para validación...")
    proveedor_ai = validar_proveedor_con_ai(factura_datos, proveedores_sap)
    if proveedor_ai:
        proveedor_ai["MetodoBusqueda"] = "AI (OpenAI)"
        proveedor_ai["Similitud"] = 0.0
        return proveedor_ai 
    
    return None

def validar_proveedor_con_ai(factura_datos, proveedores_sap):
    """
    Usa OpenAI para validar y encontrar el proveedor correcto cuando la búsqueda directa falla.
    """
    try:
        factura_datos_wrapped = {"d": factura_datos}
        system_prompt, user_prompt = get_invoice_validator_prompt(factura_datos_wrapped, proveedores_sap)
        print("  🤖 Consultando a OpenAI para validar proveedor...")
        raw_result = get_openai_answer(system_prompt, user_prompt)
        raw_result = clean_openai_json(raw_result)
        
        proveedor_info = json.loads(raw_result)
        print(f"  ✅ Proveedor validado por AI: {proveedor_info.get('SupplierName')}")
        logger.info(f"✓ Proveedor validado por AI: {proveedor_info.get('SupplierName')}")
        return proveedor_info
        
    except Exception as e:
        logger.error(f"Error en validación de proveedor con AI: {e}")
        return None

def obtener_ordenes_compra_proveedor(descripcion_factura, monto_factura, supplier_code, tax_code):
    """
    Obtiene las órdenes de compra activas para un proveedor específico.
    CORREGIDA: Usa el endpoint correcto y maneja mejor los resultados.
    """
    try:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        print({descripcion_factura,monto_factura,supplier_code})
        if not supplier_code:
            logger.warning("No se proporcionó código de proveedor para obtener órdenes de compra")
            return []
        # URL para la orden de compra
        url = f"{SAP_CONFIG['purchase_order_url']}?$filter=Supplier eq '{supplier_code}'&$expand=to_PurchaseOrderItem"
        print(f"\n🔍 BUSCANDO ÓRDENES DE COMPRA PARA PROVEEDOR {supplier_code}")
        print("="*50)
        print(f"  Método: GET")
        print(f"  URL: {url}")
        print(f"  Usuario: {SAP_CONFIG['username']}")
        
        response = requests.get(
            url,
            headers=headers,
            auth=HTTPBasicAuth(SAP_CONFIG['username'], SAP_CONFIG['password']),
            timeout=30
        )
        
        print(f"  📊 Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = safe_json_response(response)
            if data and "d" in data and "results" in data["d"]:
                oc_list = data["d"]["results"]
                if oc_list:
                    print(f"  ✅ {len(oc_list)} órdenes de compra encontradas:")
                    print("  " + "-"*40)
                    
                    # Mostrar todas las OCs con detalles
                    for i, oc in enumerate(oc_list):
                        oc_num = oc.get('PurchaseOrder', 'N/A')
                        oc_item = oc.get('PurchaseOrderItem', 'N/A')
                        oc_status = oc.get('PurchaseOrderProcessingStatus', 'N/A')
                        oc_date = oc.get('CreationDate', 'N/A')
                        
                        print(f"    {i+1:2d}. OC: {oc_num:15} | Item: {oc_item:8} | Status: {oc_status:10} | Fecha: {oc_date}")
                    
                    print("  " + "-"*40)
                    
                    # Intentar seleccionar la OC más apropiada usando IA
                    system_prompt, user_prompt = get_OC_validator_prompt(
                        descripcion_factura, 
                        monto_factura, 
                        supplier_code, 
                        oc_list
                    )
                    raw_result = get_openai_answer(system_prompt, user_prompt)
                    raw_result = clean_openai_json(raw_result)
        
                    oc_info = json.loads(raw_result)
                    
                    if oc_info and "PurchaseOrder" in oc_info:
                        print(f"  📋 OC SELECCIONADA POR IA:")
                        print(f"     • OC {oc_info.get('PurchaseOrder')} - Item {oc_info.get('PurchaseOrderItem')}")
                        
                        print(oc_info.get('PurchaseOrderQuantityUnit', ''),)
                        # Retornar como lista con un solo elemento
                        return [{
                            "PurchaseOrder": oc_info.get('PurchaseOrder'),
                            "PurchaseOrderItem": oc_info.get('PurchaseOrderItem', '00010'),
                            "DocumentCurrency": "BOB",
                            "QuantityInPurchaseOrderUnit": "1.000",
                            "PurchaseOrderQuantityUnit": oc_info.get('PurchaseOrderQuantityUnit', ''),
                            "SupplierInvoiceItemAmount": str(monto_factura),
                            "TaxCode": tax_code or oc_info.get('TaxCode', 'V0')
                        }]
                    else:
                        print(f"  ⚠️  IA no pudo identificar una OC específica")
                        logger.warning(f"IA no pudo identificar una OC específica para proveedor {supplier_code}")
                        return [] 
                else:
                    print(f"  ⚠️  No se encontraron órdenes de compra para el proveedor {supplier_code}")
                    logger.warning(f"ℹ️ No se encontraron órdenes de compra para el proveedor {supplier_code}") 
            else:
                print(f"  ⚠️  No se encontraron datos en la respuesta") 
                logger.warning("No se encontraron datos de órdenes de compra en la respuesta")
        elif response.status_code == 403:
            print(f"  ❌ ERROR 403: Permisos insuficientes")
            print(f"     Usuario: {SAP_CONFIG['username']}")
            print(f"     Endpoint: {url}")
            print(f"     Contactar al administrador SAP para agregar permisos")
            logger.warning(f"No se pudo acceder a API de órdenes de compra (Status: 403 - Forbidden)")
            return []
        else:
            print(f"  ❌ Error {response.status_code}: {response.text[:200]}")
            logger.warning(f"No se pudo acceder a API de órdenes de compra (Status: {response.status_code})")
            
    except Exception as e:
        print(f"  ❌ Excepción: {e}")
        logger.error(f"Error al obtener órdenes de compra: {e}")
    
    return []

def construir_json_factura_sap(factura_datos, proveedor_info, oc_items):
    """
    Construye el JSON final en el formato exacto que SAP espera.
    """
    print("\n" + "="*70)
    print("🏗️  CONSTRUYENDO JSON PARA SAP")
    print("="*70)
    
    if not proveedor_info:
        raise ValueError("Información del proveedor no disponible")
    
    fecha_documento = format_sap_date(factura_datos.get("DocumentDate"))    
    invoice_id = factura_datos.get("SupplierInvoiceIDByInvcgParty", "")
    
    if not invoice_id or invoice_id == "0":
        print("  ⚠️  No se encontró ID de factura, generando automático...")
        logger.warning("No se encontró ID de factura, generando automático")
        invoice_id = f"INV{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    invoice_amount = factura_datos.get("InvoiceGrossAmount", 0.0)
    invoice_amount_str = f"{invoice_amount:.0f}"
    
    cod_autorizacion = factura_datos.get("AssignmentReference", "")
    print(f"  Código de Autorización inicial: {cod_autorizacion}")
    cod_autorizacion = cod_autorizacion[:14]
    if not cod_autorizacion:
        cod_autorizacion = factura_datos.get("AuthorizationCode", "")
    if not cod_autorizacion:
        cod_autorizacion = ""
    
    print(f"  📊 DATOS PARA CONSTRUIR JSON:")
    print(f"     • N° Factura: {invoice_id}")
    print(f"     • Proveedor SAP: {proveedor_info.get('Supplier')}")
    print(f"     • Código Autorización: {cod_autorizacion[:50]}...")
    print(f"     • Monto: {invoice_amount_str} BOB")
    print(f"     • Fecha: {fecha_documento}")
    print(f"     • OCs encontradas: {len(oc_items)}")
    
    factura_json = {
        "CompanyCode": "1000",
        "DocumentDate": fecha_documento,
        "PostingDate": fecha_documento,
        "SupplierInvoiceIDByInvcgParty": invoice_id,
        "InvoicingParty": proveedor_info.get("Supplier", ""),
        "AssignmentReference": cod_autorizacion,
        "DocumentCurrency": "BOB",
        "InvoiceGrossAmount": invoice_amount_str,
        "DueCalculationBaseDate": fecha_documento,
        "TaxIsCalculatedAutomatically": True,
        "TaxDeterminationDate": fecha_documento,
        "SupplierInvoiceStatus": "B",
        "to_SuplrInvcItemPurOrdRef": {
            "results": []
        }
    }
    
    if not oc_items:
        logger.error("❌ No se encontraron órdenes de compra para esta factura")
        return None
    
    print(f"  📦 AGREGANDO {len(oc_items)} ITEMS DE OC:")
    
    for idx, oc in enumerate(oc_items, start=1):
        
        item = {
            "SupplierInvoiceItem": str(idx).zfill(5),
            "PurchaseOrder": oc.get("PurchaseOrder", ""),
            "PurchaseOrderItem": oc.get("PurchaseOrderItem", "00010"),
            "DocumentCurrency": "BOB",
            "QuantityInPurchaseOrderUnit": "1.000",
            "PurchaseOrderQuantityUnit": oc.get("PurchaseOrderQuantityUnit", ""),
            "SupplierInvoiceItemAmount": invoice_amount_str,
            "TaxCode": oc.get("TaxCode", "V0") 
        }
        factura_json["to_SuplrInvcItemPurOrdRef"]["results"].append(item)
        print(f"     • Item {idx}: OC {oc.get('PurchaseOrder')}, Item {oc.get('PurchaseOrderItem')}")
    
    return factura_json


def enviar_factura_a_sap(factura_json):
    """
    Envía la factura a SAP usando token CSRF y sesión persistente.
    Retorna la respuesta de SAP si es exitosa (201 Created).
    """
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
        
        print("\n" + "="*70)
        print("🚀 ENVIANDO FACTURA A SAP")
        print("="*70)
        print("  📤 Enviando JSON a SAP...")
        
        # Mostrar JSON que se enviará (solo estructura principal)
        print("  📄 JSON a enviar (resumen):")
        print(f"     • CompanyCode: {factura_json.get('CompanyCode')}")
        print(f"     • DocumentDate: {factura_json.get('DocumentDate')}")
        print(f"     • SupplierInvoiceIDByInvcgParty: {factura_json.get('SupplierInvoiceIDByInvcgParty')}")
        print(f"     • InvoicingParty: {factura_json.get('InvoicingParty')}")
        print(f"     • AssignmentReference: {factura_json.get('AssignmentReference')[:30]}...")
        print(f"     • InvoiceGrossAmount: {factura_json.get('InvoiceGrossAmount')}")
        print(f"     • Items: {len(factura_json.get('to_SuplrInvcItemPurOrdRef', {}).get('results', []))}")
        
        logger.info("Enviando factura a SAP...")
        
        response = session.post(
            SAP_CONFIG['invoice_post_url'],
            headers=headers_post,
            json={"d": factura_json},
            timeout=30
        )
        
        print(f"  📨 Respuesta de SAP: Status {response.status_code}")
        logger.info(f"Respuesta de SAP: Status {response.status_code}")
        
        if response.status_code in [200, 201]:
            print("  ✅ Factura creada exitosamente en SAP")
            logger.info("✅ Factura creada exitosamente en SAP")
            data = safe_json_response(response)
            return data
        else:
            print(f"  ❌ Error al crear factura en SAP: {response.status_code}")
            logger.error(f"❌ Error al crear factura en SAP: {response.status_code}")
            print(f"  📄 Detalles: {response.text[:500]}")
            logger.error(f"Detalles: {response.text[:500]}")
            return None
            
    except Exception as e:
        logger.error(f"Error en envío a SAP: {e}")
        return None
    finally:
        if session:
            session.close()

# ============================================================================
# Tools - FLUJO COMPLETO DE PROCESAMIENTO DE FACTURA
# ============================================================================

def procesar_factura_completa(texto_factura):
    """
    FUNCIÓN PRINCIPAL - Procesa una factura desde texto extraído por el OCR hasta carga en SAP.
    COMPLETA: Incluye todos los pasos del flujo.
    """
    
    logger.info("\n" + "="*70)
    logger.info("\n INICIANDO PROCESO COMPLETO DE CARGA DE FACTURA")
    logger.info("="*70)
    
    resultado = {
        'success': False,
        'message': '',
        'data': None,
        'error': None
    }
    
    try:
        # ====================================================================
        # PASO 1: EXTRACCIÓN DE DATOS DE LA FACTURA (OCR -> Estructurado)
        # ====================================================================
        print("\n" + "="*70)
        print("1️⃣ EXTRACCIÓN DE DATOS DE FACTURA")
        print("="*70)
        logger.info("\n1️⃣ EXTRACCIÓN DE DATOS DE FACTURA")
        logger.info("-"*40)
        
        factura_datos = extraer_datos_factura_desde_texto(texto_factura)
        
        if not factura_datos:
            error_msg = "No se pudieron extraer datos de la factura"
            logger.error(error_msg)
            resultado['error'] = error_msg
            resultado['message'] = error_msg
            return resultado
        
        # Mostrar datos transformados
        print("\n" + "="*70)
        print("📋 DATOS TRANSFORMADOS PARA PROCESAMIENTO:")
        print("="*70)
        for key, value in factura_datos.items():
            print(f"  {key}: {value}")
        print("="*70)
        
        # ====================================================================
        # PASO 2: OBTENCIÓN Y VALIDACIÓN DE PROVEEDOR EN SAP
        # ====================================================================
        print("\n" + "="*70)
        print("2️⃣ VALIDACIÓN DE PROVEEDOR EN SAP")
        print("="*70)
        logger.info("\n2️⃣ VALIDACIÓN DE PROVEEDOR EN SAP")
        logger.info("-"*40)
        
        proveedores_sap = obtener_proveedores_sap()
        if not proveedores_sap:
            error_msg = "No se pudieron obtener proveedores de SAP"
            logger.error(error_msg)
            resultado['error'] = error_msg
            resultado['message'] = error_msg
            return resultado
        #aqui hacer cambio para TaxCode
        proveedor_info = buscar_proveedor_en_sap(factura_datos, proveedores_sap)
        if not proveedor_info:
            error_msg = f"Proveedor no encontrado en SAP: {factura_datos.get('SupplierName')}"
            logger.error(error_msg)
            resultado['error'] = error_msg
            resultado['message'] = error_msg
            return resultado
        
        print("\n" + "="*70)
        print("✅ PROVEEDOR VALIDADO:")
        print("="*70)
        print(f"  Código SAP: {proveedor_info.get('Supplier')}")
        print(f"  Nombre: {proveedor_info.get('SupplierName')}")
        print(f"  Nombre Completo: {proveedor_info.get('SupplierFullName')}")
        print(f"  Tax: {proveedor_info.get('TaxNumber')}")
        print(f"  Grupo: {proveedor_info.get('SupplierAccountGroup')}")
        print("="*70)
        
        logger.info("✓ Proveedor validado:")
        logger.info(f"  Código SAP: {proveedor_info.get('Supplier')}")
        logger.info(f"  Nombre: {proveedor_info.get('SupplierName')}")
        logger.info(f"  Tax: {proveedor_info.get('TaxNumber')}")
        
        # ====================================================================
        # PASO 3: OBTENCIÓN DE ÓRDENES DE COMPRA ASOCIADAS
        # ====================================================================
        print("\n" + "="*70)
        print("3️⃣ BUSQUEDA DE ÓRDENES DE COMPRA")
        print("="*70)
        logger.info("\n3️⃣ BUSQUEDA DE ÓRDENES DE COMPRA")
        logger.info("-"*40)
        
        supplier_code = proveedor_info.get("Supplier", "")
        if not supplier_code:
            error_msg = "Código de proveedor no disponible"
            logger.error(error_msg)
            resultado['error'] = error_msg
            resultado['message'] = error_msg
            return resultado
        #descripcion_factura = factura_datos.get("description", "")
        items = factura_datos.get("Items") or factura_datos.get("items") or []
        if isinstance(items, dict):
            items = [items]
        descripcion_parts = []
        if isinstance(items, list):
            for it in items:
                if not isinstance(it, dict):
                    continue
                for k in ("Description", "Descripcion", "ItemDescription", "description"):
                    v = it.get(k)
                    if v:
                        descripcion_parts.append(str(v).strip())
                        break
        descripcion_factura = "; ".join(descripcion_parts) if descripcion_parts else factura_datos.get("Description") or factura_datos.get("description") or ""

        monto_factura = factura_datos.get("InvoiceGrossAmount", "")
        supplier_code = proveedor_info.get("Supplier", "")
        tax_code = proveedor_info.get("TaxCode", "")
        # Pasar la descripción como string y las OCs se pasan como lista al prompt internamente
        oc_items = obtener_ordenes_compra_proveedor(descripcion_factura, monto_factura, supplier_code, tax_code)
        
        # CRÍTICO: Validar que tenemos OC para continuar
        if not oc_items:
            error_msg = f"No se encontraron órdenes de compra para el proveedor {supplier_code}"
            print(f"\n❌ ERROR: {error_msg}")
            print("   El proceso se detiene. Esta factura no puede ser cargada sin OC.")
            logger.error(error_msg)
            logger.error("El proceso se detiene. Esta factura no puede ser cargada sin OC.")
            resultado['error'] = error_msg
            resultado['message'] = "Factura no tiene OC asociada en SAP"
            return resultado
        
        print(f"\n✅ {len(oc_items)} órdenes de compra encontradas")
        logger.info(f"✓ {len(oc_items)} órdenes de compra encontradas")
        
        # ====================================================================
        # PASO 4: CONSTRUCCIÓN DEL JSON PARA SAP
        # ====================================================================
        print("\n" + "="*70)
        print("4️⃣ CONSTRUCCIÓN DE JSON PARA SAP")
        print("="*70)
        logger.info("\n4️⃣ CONSTRUCCIÓN DE JSON PARA SAP")
        logger.info("-"*40)
        
        factura_json = construir_json_factura_sap(factura_datos, proveedor_info, oc_items)
        
        if not factura_json:
            error_msg = "No se pudo construir el JSON para SAP"
            logger.error(error_msg)
            resultado['error'] = error_msg
            resultado['message'] = error_msg
            return resultado
        
        # Mostrar JSON final construido
        print("\n" + "="*70)
        print("📄 JSON FINAL CONSTRUIDO PARA SAP:")
        print("="*70)
        print(json.dumps(factura_json, indent=2, ensure_ascii=False))
        print("="*70)
        
        # ====================================================================
        # PASO 5: ENVÍO A SAP
        # ====================================================================
        print("\n" + "="*70)
        print("5️⃣ ENVÍO A SAP")
        print("="*70)
        logger.info("\n5️⃣ ENVÍO A SAP")
        logger.info("-"*40)
        
        respuesta_sap = enviar_factura_a_sap(factura_json)
        
        if not respuesta_sap:
            error_msg = "No se pudo enviar la factura a SAP"
            logger.error(error_msg)
            resultado['error'] = error_msg
            resultado['message'] = error_msg
            return resultado
        
        # ====================================================================
        # ÉXITO: Factura cargada correctamente
        # ====================================================================
        print("\n" + "="*70)
        print("🎉 FACTURA CREADA EXITOSAMENTE EN SAP")
        print("="*70)
        logger.info("\n" + "="*70)
        logger.info("🎉 FACTURA CREADA EXITOSAMENTE EN SAP")
        logger.info("="*70)
        
        resultado['success'] = True
        resultado['message'] = "Factura cargada exitosamente en SAP"
        resultado['data'] = {
            'factura_id': factura_json.get('SupplierInvoiceIDByInvcgParty'),
            'proveedor': proveedor_info.get('SupplierName'),
            'proveedor_codigo': proveedor_info.get('Supplier'),
            'monto': factura_json.get('InvoiceGrossAmount'),
            'codigo_autorizacion': factura_json.get('AssignmentReference'),
            'oc_count': len(oc_items),
            'respuesta_sap': respuesta_sap,
            'json_final': factura_json  # Incluir el JSON final en la respuesta
        }
        
        return resultado
        
    except Exception as e:
        # ====================================================================
        # MANEJO DE ERRORES GLOBALES
        # ====================================================================
        error_msg = f"Error inesperado en el procesamiento: {str(e)}"
        print(f"\n❌ ERROR: {error_msg}")
        logger.error(error_msg)
        logger.exception(e)
        
        resultado['error'] = error_msg
        resultado['message'] = "Error en el procesamiento de la factura"
        
        return resultado

        
    except Exception as e:
        # ====================================================================
        # MANEJO DE ERRORES GLOBALES
        # ====================================================================
        error_msg = f"Error inesperado en el procesamiento: {str(e)}"
        print(f"\n❌ ERROR: {error_msg}")
        logger.error(error_msg)
        logger.exception(e)
        
        resultado['error'] = error_msg
        resultado['message'] = "Error en el procesamiento de la factura"
        
        return resultado

def extraer_texto_pdf(ruta_gcs: str) -> dict:
    """ 
    Extrae datos de una factura desde una ruta GCS usando OCR y LLM.
    """
    try:
        logger.info(f"Iniciando extracción de datos de factura desde: {ruta_gcs}")
        
        # Descargar PDF temporalmente
        ruta_temp = download_pdf_to_tempfile(ruta_gcs)
        logger.info(f"Archivo temporal descargado: {ruta_temp}")
        
        # OCR
        logger.info("Extrayendo texto con Cloud Vision")
        texto_factura = get_transcript_document_cloud_vision(ruta_temp)
        logger.info(f"Texto extraído (primeros 2000 caracteres):\n{texto_factura[:2000]}")
        
        return {
            "status": "success",
            "data": texto_factura
        }
        
    except Exception as e:
        error_msg = f"Error al extraer datos de la factura: {str(e)}"
        logger.error(error_msg)
        return {"status": "error", "error": str(e)}
    
    finally:
        # Eliminar archivo temporal si existe
        try:
            if os.path.exists(ruta_temp):
                os.remove(ruta_temp)
                logger.info(f"Archivo temporal eliminado: {ruta_temp}")
        except Exception as e:
            logger.warning(f"No se pudo eliminar el archivo temporal: {str(e)}")


        
        
    
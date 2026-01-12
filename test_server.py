# procesar_factura_avanzado.py

import requests
import tempfile
import os
import json
import re
import logging
from datetime import datetime
from typing import Dict, Any, List
import PyPDF2

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ProcesadorFacturas:
    """Clase para procesar facturas desde URLs"""
    
    def __init__(self):
        self.patrones = self._inicializar_patrones()
        
    def _inicializar_patrones(self):
        """Inicializa todos los patrones de búsqueda"""
        return {
            'numero_factura': [
                r'FACTURA\s*N[°:\s]*(\d+)',
                r'Factura\s*N°?\s*:\s*(\d+)',
                r'No\.?\s*Factura\s*:\s*(\d+)',
                r'N°?\s*Factura\s*:\s*(\d+)',
                r'Factura\s*No\.?\s*(\d+)',
                r'Invoice\s*No\.?\s*:\s*(\d+)'
            ],
            'nit_proveedor': [
                r'NIT\s*:\s*([\d-]+)',
                r'NIT\s*([\d-]+)',
                r'RUC\s*:\s*([\d-]+)',
                r'RUC\s*([\d-]+)',
                r'N\.I\.T\.\s*:\s*([\d-]+)'
            ],
            'nit_cliente': [
                r'NIT/CI/CEX:\s*([\d-]+)',
                r'CI/NIT:\s*([\d-]+)',
                r'NIT\s*Cliente:\s*([\d-]+)',
                r'C\.I\.\s*:\s*([\d-]+)'
            ],
            'monto_total': [
                r'TOTAL\s*Bs\s*([\d\.,]+)',
                r'MONTO\s*A\s*PAGAR\s*Bs\s*([\d\.,]+)',
                r'IMPORTE\s*TOTAL\s*Bs\s*([\d\.,]+)',
                r'TOTAL\s*:\s*Bs\s*([\d\.,]+)',
                r'MONTO\s*TOTAL\s*Bs\s*([\d\.,]+)',
                r'Total\s*General\s*Bs\s*([\d\.,]+)'
            ],
            'fecha': [
                r'Fecha:\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
                r'Fecha\s*Factura:\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
                r'Fecha\s*Emisi[oó]n:\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
                r'FECHA\s*:\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
                r'Date:\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})'
            ],
            'codigo_autorizacion': [
                r'C[OÓ]D(?:IGO)?\s*AUTORIZACI[OÓ]N\s*[:]?\s*([A-Z0-9]+)',
                r'AUTORIZACI[OÓ]N\s*[:]?\s*([A-Z0-9]+)',
                r'C[OÓ]D(?:\.)?\s*([A-Z0-9]{20,})',
                r'Código\s*de\s*Autorización:\s*([A-Z0-9]+)',
                r'C\.A\.\s*:\s*([A-Z0-9]+)'
            ],
            'nombre_proveedor': [
                # Patrones comunes para nombres de empresas
                r'^(?!.*(NIT|RUC|CI|Fecha|Total|Bs|Código))[A-ZÁÉÍÓÚÑ\s\.\-&]{5,}$'
            ]
        }
    
    def descargar_pdf(self, url: str) -> str:
        """Descarga PDF desde URL"""
        try:
            logger.info(f"Descargando: {url}")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            # Verificar que es un PDF
            content_type = response.headers.get('content-type', '')
            if 'pdf' not in content_type.lower():
                logger.warning(f"El archivo podría no ser PDF: {content_type}")
            
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            temp_file.write(response.content)
            temp_file.close()
            
            size_mb = os.path.getsize(temp_file.name) / (1024 * 1024)
            logger.info(f"✓ PDF descargado: {temp_file.name} ({size_mb:.2f} MB)")
            
            return temp_file.name
            
        except Exception as e:
            logger.error(f"❌ Error al descargar: {e}")
            return None
    
    def extraer_texto(self, pdf_path: str) -> str:
        """Extrae texto del PDF"""
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                texto_total = ""
                
                for i, page in enumerate(pdf_reader.pages):
                    texto = page.extract_text()
                    if texto:
                        texto_total += texto + "\n\n"  # Separador entre páginas
                    
                    # Log de progreso
                    if (i + 1) % 5 == 0:
                        logger.info(f"  Procesando página {i + 1}/{len(pdf_reader.pages)}")
                
                logger.info(f"✓ {len(pdf_reader.pages)} páginas procesadas")
                logger.info(f"✓ {len(texto_total):,} caracteres extraídos")
                
                return texto_total
                
        except Exception as e:
            logger.error(f"Error al extraer texto: {e}")
            return ""
    
    def buscar_con_patrones(self, texto: str, campo: str) -> str:
        """Busca un valor usando múltiples patrones"""
        if campo not in self.patrones:
            return ""
        
        for patron in self.patrones[campo]:
            try:
                match = re.search(patron, texto, re.IGNORECASE | re.MULTILINE)
                if match:
                    return match.group(1).strip()
            except:
                continue
        return ""
    
    def extraer_nombre_proveedor(self, texto: str) -> str:
        """Extrae el nombre del proveedor usando heurísticas"""
        lineas = [line.strip() for line in texto.split('\n') if line.strip()]
        
        # Buscar líneas que parezcan nombres de empresas
        for i, linea in enumerate(lineas):
            # Después de NIT/RUC
            if re.search(r'(NIT|RUC|N\.I\.T\.)\s*:', linea, re.IGNORECASE):
                # Verificar siguientes líneas
                for j in range(1, min(4, len(lineas) - i)):
                    candidato = lineas[i + j]
                    # Validar que sea un nombre razonable
                    if (len(candidato) > 3 and 
                        len(candidato) < 100 and
                        not re.search(r'\d{5,}', candidato) and
                        not re.search(r'(http|www|@|\.com|\.bo|telefono|tel|fax)', candidato, re.IGNORECASE)):
                        return candidato
        
        # Buscar por patrones de nombres de empresa
        patrones_empresa = [
            r'^[A-ZÁÉÍÓÚÑ\s\.\-&]{5,}(?:S\.A\.|S\.R\.L\.|LTDA|E\.I\.R\.L\.|S\.A\.S\.)?$',
            r'^[A-Z][a-záéíóúñ\s\.\-&]{5,}(?:S\.A\.|S\.R\.L\.|LTDA|E\.I\.R\.L\.)?$'
        ]
        
        for linea in lineas:
            for patron in patrones_empresa:
                if re.match(patron, linea.strip()):
                    return linea.strip()
        
        return ""
    
    def extraer_productos(self, texto: str) -> List[Dict[str, str]]:
        """Extrae información de productos"""
        productos = []
        lineas = texto.split('\n')
        
        # Buscar tabla de productos
        for i, linea in enumerate(lineas):
            # Patrón de línea de producto (código, descripción, cantidad, precio)
            if (re.search(r'\b\d{5,}\b', linea) and  # Tiene un código
                re.search(r'\d+\.?\d*\s*\d+\.?\d*,\d{2}', linea)):  # Tiene precios
                
                producto = {
                    'linea_original': linea.strip(),
                    'numero_linea': i + 1
                }
                
                # Intentar extraer componentes
                partes = re.split(r'\s{2,}', linea)  # Separar por múltiples espacios
                if len(partes) >= 4:
                    producto['codigo'] = partes[0].strip() if partes[0] else ''
                    producto['descripcion'] = partes[1].strip() if len(partes) > 1 else ''
                    producto['cantidad'] = partes[2].strip() if len(partes) > 2 else ''
                    producto['precio'] = partes[3].strip() if len(partes) > 3 else ''
                
                productos.append(producto)
        
        return productos
    
    def procesar(self, url: str) -> Dict[str, Any]:
        """Procesa una factura desde URL"""
        logger.info("="*70)
        logger.info(f"PROCESANDO FACTURA: {url}")
        logger.info("="*70)
        
        resultado = {
            'success': False,
            'url': url,
            'timestamp': datetime.now().isoformat(),
            'datos': {},
            'estadisticas': {},
            'error': None
        }
        
        temp_path = None
        
        try:
            # 1. Descargar
            temp_path = self.descargar_pdf(url)
            if not temp_path:
                raise ValueError("No se pudo descargar el PDF")
            
            # 2. Extraer texto
            texto = self.extraer_texto(temp_path)
            if len(texto.strip()) < 100:
                raise ValueError("Texto insuficiente extraído del PDF")
            
            resultado['estadisticas']['caracteres'] = len(texto)
            resultado['estadisticas']['lineas'] = len(texto.split('\n'))
            
            # Guardar texto para análisis
            with open("texto_analisis.txt", "w", encoding="utf-8") as f:
                f.write(texto)
            
            # 3. Extraer datos
            datos = {}
            
            # Campos básicos
            campos_basicos = ['numero_factura', 'nit_proveedor', 'nit_cliente', 
                            'monto_total', 'fecha', 'codigo_autorizacion']
            
            for campo in campos_basicos:
                valor = self.buscar_con_patrones(texto, campo)
                if valor:
                    datos[campo] = valor
                    logger.info(f"✓ {campo}: {valor}")
            
            # Nombre proveedor (heurística especial)
            nombre_proveedor = self.extraer_nombre_proveedor(texto)
            if nombre_proveedor:
                datos['nombre_proveedor'] = nombre_proveedor
                logger.info(f"✓ nombre_proveedor: {nombre_proveedor}")
            
            # Productos
            productos = self.extraer_productos(texto)
            if productos:
                datos['productos'] = productos
                datos['num_productos'] = len(productos)
                logger.info(f"✓ Productos encontrados: {len(productos)}")
            
            resultado['datos'] = datos
            resultado['success'] = True
            resultado['estadisticas']['campos_encontrados'] = len(datos)
            
            # 4. Guardar resultados
            self.guardar_resultados(resultado)
            
            return resultado
            
        except Exception as e:
            logger.error(f"Error en procesamiento: {e}")
            resultado['error'] = str(e)
            return resultado
            
        finally:
            # Limpiar
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except:
                    pass
    
    def guardar_resultados(self, resultado: Dict[str, Any]):
        """Guarda los resultados en archivos JSON"""
        try:
            # Resultado completo
            with open("resultado_factura.json", "w", encoding="utf-8") as f:
                json.dump(resultado, f, indent=2, ensure_ascii=False)
            
            # Solo datos extraídos
            datos_simples = {
                'numero_factura': resultado['datos'].get('numero_factura'),
                'proveedor': resultado['datos'].get('nombre_proveedor'),
                'nit_proveedor': resultado['datos'].get('nit_proveedor'),
                'fecha': resultado['datos'].get('fecha'),
                'monto_total': resultado['datos'].get('monto_total'),
                'codigo_autorizacion': resultado['datos'].get('codigo_autorizacion')
            }
            
            with open("datos_principales.json", "w", encoding="utf-8") as f:
                json.dump(datos_simples, f, indent=2, ensure_ascii=False)
            
            logger.info("✓ Resultados guardados en archivos JSON")
            
        except Exception as e:
            logger.warning(f"No se pudieron guardar resultados: {e}")

def main():
    """Función principal"""
    print("="*70)
    print("PROCESADOR AVANZADO DE FACTURAS")
    print("="*70)
    
    # URL de prueba
    url = "https://storage.googleapis.com/rpa_facturacion/entrada_facturas/Jordi_Salas__jorditoandr0000%40gmail.com_/1765638550318_Factura-prueba2.pdf"
    
    print(f"\n📄 Factura a procesar:")
    print(f"   {url}")
    
    print("\n🔄 Iniciando procesamiento...")
    
    # Crear procesador
    procesador = ProcesadorFacturas()
    
    # Procesar
    resultado = procesador.procesar(url)
    
    # Mostrar resultados
    print("\n" + "="*70)
    if resultado['success']:
        print("✅ PROCESAMIENTO EXITOSO")
        print("="*70)
        
        datos = resultado['datos']
        
        print("\n📋 DATOS EXTRAÍDOS:")
        print("-" * 40)
        
        for clave, valor in datos.items():
            if clave not in ['productos', 'num_productos']:
                print(f"  {clave}: {valor}")
        
        if 'productos' in datos:
            print(f"\n📦 PRODUCTOS ({datos.get('num_productos', 0)}):")
            for i, producto in enumerate(datos['productos'][:3], 1):  # Mostrar solo 3
                print(f"  {i}. {producto.get('linea_original', '')[:80]}...")
        
        print(f"\n📊 ESTADÍSTICAS:")
        print(f"  - Caracteres procesados: {resultado['estadisticas'].get('caracteres', 0):,}")
        print(f"  - Líneas analizadas: {resultado['estadisticas'].get('lineas', 0)}")
        print(f"  - Campos encontrados: {resultado['estadisticas'].get('campos_encontrados', 0)}")
        
    else:
        print("❌ ERROR EN PROCESAMIENTO")
        print("="*70)
        print(f"Error: {resultado.get('error', 'Desconocido')}")
    
    print("\n" + "="*70)
    print("💾 ARCHIVOS GENERADOS:")
    print("  - resultado_factura.json (resultado completo)")
    print("  - datos_principales.json (datos principales)")
    print("  - texto_analisis.txt (texto extraído)")
    print("="*70)
    
    return resultado

if __name__ == "__main__":
    # Verificar dependencias
    try:
        import requests
        import PyPDF2
        print("✅ Dependencias verificadas")
    except ImportError as e:
        print(f"❌ Error: {e}")
        print("\n📦 Instala las dependencias:")
        print("   pip install requests PyPDF2")
        exit(1)
    
    main()
# scripts/flujo_completo_verificado.py
"""
Flujo completo de procesamiento de facturas CON verificación por etapas.

Uso:
    python -m scripts.flujo_completo_verificado <ruta_pdf> [opciones]

Opciones:
    --enviar, -e          Enviar la factura a SAP
    --no-comparar-ocr     No comparar múltiples OCRs
    --no-exit-on-fail     Continuar aunque falle verificación
    --exit-after N        Terminar después de etapa N (desarrollo incremental)
    --ground-truth PATH   Ruta a archivo de ground truth personalizado

Ejemplos:
    # Solo verificar OCR (etapa 1)
    python -m scripts.flujo_completo_verificado factura.pdf --exit-after 1

    # Verificar hasta parsing (etapa 2)
    python -m scripts.flujo_completo_verificado factura.pdf --exit-after 2

    # Flujo completo sin enviar
    python -m scripts.flujo_completo_verificado factura.pdf

    # Flujo completo enviando a SAP
    python -m scripts.flujo_completo_verificado factura.pdf --enviar
"""

import sys
import json
import logging
from datetime import datetime
from pathlib import Path

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Imports del proyecto
from tools import (
    extraer_texto_pdf,
    parsear_datos_factura,
    validar_proveedor_sap,
    obtener_ordenes_compra,
    verificar_entrada_material,
    construir_json_factura,
    enviar_factura_sap,
    notificar_error_admin,
)
from utilities.file_storage import download_pdf_to_tempfile

# Imports del sistema de verificación
from verification.ground_truth import GroundTruthManager
from verification.ocr_comparator import OCRComparator
from verification.stage_verifier import StageVerifier
from verification.execution_logger import ExecutionLogger
from verification.schemas import (
    StageResult,
    StageStatus,
    VerificationResult,
    ExecutionResult,
)


class StageFailure(Exception):
    """Excepción para fallos en etapas."""
    pass


class FlujoVerificado:
    """
    Ejecutor del flujo de facturas con verificación por etapas.

    Características:
    - Verificación contra ground truth en cada etapa
    - Comparación de múltiples motores OCR
    - Logging detallado de ejecuciones
    - Modo desarrollo con sys.exit() configurable
    """

    # Definición de etapas
    ETAPAS = {
        1: ("ocr", "Extracción de texto con OCR"),
        2: ("parsing", "Parsing de datos estructurados"),
        3: ("validacion_proveedor", "Validación de proveedor en SAP"),
        4: ("busqueda_oc", "Búsqueda de órdenes de compra"),
        5: ("verificacion_migo", "Verificación de entrada de material (MIGO)"),
        6: ("construccion_json", "Construcción de JSON para SAP"),
        7: ("envio_sap", "Envío a SAP"),
    }

    def __init__(
        self,
        ground_truth_path: str = None,
        comparar_ocr: bool = False,
        exit_on_failure: bool = True,
        exit_after_stage: int = None,
    ):
        """
        Inicializa el flujo verificado.

        Args:
            ground_truth_path: Ruta al archivo de ground truth
            comparar_ocr: Si True, compara resultados de múltiples OCR
            exit_on_failure: Si True, termina con sys.exit() si falla verificación
            exit_after_stage: Etapa después de la cual terminar (para desarrollo)
        """
        self.ground_truth_manager = GroundTruthManager(ground_truth_path)
        self.ocr_comparator = OCRComparator()
        self.execution_logger = ExecutionLogger()

        self.comparar_ocr = comparar_ocr
        self.exit_on_failure = exit_on_failure
        self.exit_after_stage = exit_after_stage

        # Estado de la ejecución
        self.ground_truth = None
        self.verifier = None
        self.ruta_temp_pdf = None

    def ejecutar(self, source: str, enviar: bool = False) -> dict:
        """
        Ejecuta el flujo completo con verificación.

        Args:
            source: Ruta al PDF (local, gs://, https://)
            enviar: Si True, envía la factura a SAP

        Returns:
            Diccionario con resultado completo
        """
        filename = Path(source).name

        # Iniciar logging
        self.execution_logger.start_execution(
            archivo_entrada=filename,
            ground_truth_usado=str(self.ground_truth_manager.ground_truth_path),
            modo="verificacion" if self.exit_on_failure else "produccion"
        )

        # Cargar ground truth
        self.ground_truth = self.ground_truth_manager.get_entry_for_file(filename)
        self.verifier = StageVerifier(self.ground_truth)

        if not self.ground_truth:
            print(f"\n[AVISO] No hay ground truth para '{filename}'. Continuando sin verificación.")

        print("\n" + "=" * 70)
        print("FLUJO DE PROCESAMIENTO DE FACTURA (CON VERIFICACION)")
        print("=" * 70)
        print(f"  Archivo: {source}")
        print(f"  Ground Truth: {'Disponible' if self.ground_truth else 'No disponible'}")
        print(f"  Comparar OCR: {'Sí' if self.comparar_ocr else 'No'}")
        print(f"  Exit on Failure: {'Sí' if self.exit_on_failure else 'No'}")
        if self.exit_after_stage:
            print(f"  Exit After Stage: {self.exit_after_stage}")
        print("=" * 70)

        # Variables para almacenar resultados
        resultado = {
            "success": False,
            "texto_extraido": None,
            "datos_factura": None,
            "proveedor_info": None,
            "oc_items": None,
            "migo_info": None,
            "factura_json": None,
        }

        try:
            # Descargar PDF si es necesario
            self.ruta_temp_pdf = download_pdf_to_tempfile(source)

            # ETAPA 1: OCR
            resultado["texto_extraido"] = self._ejecutar_etapa_ocr()
            self._check_exit(1)

            # ETAPA 2: Parsing
            resultado["datos_factura"] = self._ejecutar_etapa_parsing(
                resultado["texto_extraido"]
            )
            self._check_exit(2)

            # ETAPA 3: Validación Proveedor
            resultado["proveedor_info"] = self._ejecutar_etapa_proveedor(
                resultado["datos_factura"]
            )
            self._check_exit(3)

            # ETAPA 4: Búsqueda OC (Selección Determinística)
            oc_result = self._ejecutar_etapa_oc(
                resultado["datos_factura"],
                resultado["proveedor_info"]
            )
            resultado["oc_data"] = oc_result
            resultado["oc_items"] = oc_result.get("oc_items", [])
            resultado["needs_migo"] = oc_result.get("needs_migo", False)
            self._check_exit(4)

            # ETAPA 5: Verificación entrada material (MIGO) - OBLIGATORIA
            # Siempre verificamos que exista MIGO, needs_migo solo define si se incluye en JSON
            resultado["migo_result"] = self._ejecutar_etapa_migo(
                resultado["datos_factura"],
                oc_result
            )
            self._check_exit(5)

            # Solo usar reference_document si needs_migo es True
            reference_document = None
            if resultado["needs_migo"]:
                reference_document = resultado["migo_result"].get("reference_document")

            # ETAPA 6: Construcción JSON
            resultado["factura_json"] = self._ejecutar_etapa_json(
                resultado["datos_factura"],
                resultado["proveedor_info"],
                resultado["oc_items"],
                needs_migo=resultado["needs_migo"],
                reference_document=reference_document
            )
            self._check_exit(6)

            # ETAPA 7: Envío SAP (opcional)
            if enviar:
                self._ejecutar_etapa_envio(resultado["factura_json"])
            else:
                self._registrar_etapa_skip(7, "Envío a SAP omitido (modo simulación)")

            resultado["success"] = True

        except StageFailure as e:
            logger.error(f"Fallo en etapa: {e}")
            resultado["error"] = str(e)
            try:
                notificar_error_admin(error=str(e))
            except Exception:
                print("Error al enviar notificación de error por correo.")
                pass
        except Exception as e:
            logger.exception(f"Error inesperado: {e}")
            resultado["error"] = str(e)
        finally:
            # Guardar log
            log_path = self.execution_logger.finish_execution()
            resultado["log_path"] = log_path
            print(f"\n[LOG] Guardado en: {log_path}")

        return resultado

    def _ejecutar_etapa_ocr(self) -> str:
        """Ejecuta la etapa de OCR con verificación."""
        etapa_num = 1
        nombre, descripcion = self.ETAPAS[etapa_num]
        timestamp_inicio = datetime.now()

        print(f"\n{'='*70}")
        print(f"ETAPA {etapa_num}: {descripcion.upper()}")
        print(f"{'='*70}")

        texto_principal = None
        texto_alternativo = None
        comparacion_ocr = None

        try:
            # Comparar OCR si está habilitado
            if self.comparar_ocr:
                print("  Comparando motores OCR...")
                comparacion_ocr, texto_principal, texto_alternativo = \
                    self.ocr_comparator.compare_ocr_results(
                        self.ruta_temp_pdf,
                        primary_method="google_cloud_vision",
                        alternative_method="pymupdf"
                    )

                print(f"    - Similitud: {comparacion_ocr.similitud_texto:.2%}")
                print(f"    - Recomendación: {comparacion_ocr.recomendacion}")

                # Guardar contexto para análisis
                if texto_principal:
                    self.execution_logger.add_context("texto_google_vision_preview", texto_principal[:1000])
                if texto_alternativo:
                    self.execution_logger.add_context("texto_pymupdf_preview", texto_alternativo[:1000])
                self.execution_logger.add_context("ocr_combinado_disponible", True)
            else:
                # Solo usar Google Cloud Vision via la tool
                resultado = extraer_texto_pdf(self.ruta_temp_pdf)
                if resultado.get("status") != "success":
                    raise StageFailure(f"Error en OCR: {resultado.get('error')}")
                texto_principal = resultado["data"]

            if not texto_principal:
                raise StageFailure("No se pudo extraer texto del PDF")

            print(f"  Texto extraído: {len(texto_principal)} caracteres")
            print(f"  Preview: {texto_principal[:300]}...")

            # Verificar OCR
            verificacion = self.verifier.verify_ocr(texto_principal)
            self._print_verification(verificacion)

            # Registrar etapa
            stage_result = StageResult(
                etapa=etapa_num,
                nombre=nombre,
                descripcion=descripcion,
                timestamp_inicio=timestamp_inicio,
                timestamp_fin=datetime.now(),
                duracion_ms=int((datetime.now() - timestamp_inicio).total_seconds() * 1000),
                status=StageStatus.SUCCESS,
                verificacion=verificacion,
                comparacion_ocr=comparacion_ocr,
                data={
                    "texto_extraido_preview": texto_principal[:500],
                    "caracteres_totales": len(texto_principal),
                    "metodo_ocr": "google_cloud_vision"
                }
            )
            self.execution_logger.add_stage_result(stage_result)

            # Verificar si falló
            if verificacion.resultado == VerificationResult.FAIL and self.exit_on_failure:
                raise StageFailure(f"Verificación OCR fallida: {verificacion.mensaje}")

            return texto_principal

        except StageFailure:
            raise
        except Exception as e:
            self._registrar_etapa_error(etapa_num, nombre, descripcion, timestamp_inicio, str(e))
            raise StageFailure(f"Error en OCR: {e}")

    def _ejecutar_etapa_parsing(self, texto: str) -> dict:
        """Ejecuta la etapa de parsing con verificación."""
        etapa_num = 2
        nombre, descripcion = self.ETAPAS[etapa_num]
        timestamp_inicio = datetime.now()

        print(f"\n{'='*70}")
        print(f"ETAPA {etapa_num}: {descripcion.upper()}")
        print(f"{'='*70}")

        try:
            resultado = parsear_datos_factura(texto)

            if resultado.get("status") != "success":
                raise StageFailure(f"Error en parsing: {resultado.get('error')}")

            datos = resultado["data"]
            print(f"  Datos parseados:")
            for key, value in datos.items():
                value_str = str(value)
                if len(value_str) > 80:
                    value_str = value_str[:80] + "..."
                print(f"    - {key}: {value_str}")

            # Verificar parsing
            verificacion = self.verifier.verify_parsing(datos)
            self._print_verification(verificacion)

            # Registrar etapa
            stage_result = StageResult(
                etapa=etapa_num,
                nombre=nombre,
                descripcion=descripcion,
                timestamp_inicio=timestamp_inicio,
                timestamp_fin=datetime.now(),
                duracion_ms=int((datetime.now() - timestamp_inicio).total_seconds() * 1000),
                status=StageStatus.SUCCESS,
                verificacion=verificacion,
                data={"datos_parseados": datos}
            )
            self.execution_logger.add_stage_result(stage_result)

            if verificacion.resultado == VerificationResult.FAIL and self.exit_on_failure:
                raise StageFailure(f"Verificación parsing fallida: {verificacion.mensaje}")

            return datos

        except StageFailure:
            raise
        except Exception as e:
            self._registrar_etapa_error(etapa_num, nombre, descripcion, timestamp_inicio, str(e))
            raise StageFailure(f"Error en parsing: {e}")

    def _ejecutar_etapa_proveedor(self, datos_factura: dict) -> dict:
        """Ejecuta la etapa de validación de proveedor."""
        etapa_num = 3
        nombre, descripcion = self.ETAPAS[etapa_num]
        timestamp_inicio = datetime.now()

        print(f"\n{'='*70}")
        print(f"ETAPA {etapa_num}: {descripcion.upper()}")
        print(f"{'='*70}")

        try:
            nombre_proveedor = datos_factura.get('SupplierName', '')
            nit_proveedor = datos_factura.get('SupplierTaxNumber', '')

            print(f"  Buscando proveedor: {nombre_proveedor} (NIT: {nit_proveedor})")

            resultado = validar_proveedor_sap(nombre_proveedor, nit_proveedor)

            if resultado.get("status") == "not_found":
                raise StageFailure(f"Proveedor no encontrado: {resultado.get('error')}")
            elif resultado.get("status") == "error":
                raise StageFailure(f"Error en validación: {resultado.get('error')}")

            proveedor = resultado["data"]
            print(f"  Proveedor encontrado:")
            print(f"    - Código SAP: {proveedor.get('Supplier')}")
            print(f"    - Nombre: {proveedor.get('SupplierName')}")
            print(f"    - Tax: {proveedor.get('TaxNumber')}")
            print(f"    - Método: {proveedor.get('MetodoBusqueda', 'N/A')}")

            # Verificar proveedor
            verificacion = self.verifier.verify_proveedor(proveedor)
            self._print_verification(verificacion)

            # Registrar etapa
            stage_result = StageResult(
                etapa=etapa_num,
                nombre=nombre,
                descripcion=descripcion,
                timestamp_inicio=timestamp_inicio,
                timestamp_fin=datetime.now(),
                duracion_ms=int((datetime.now() - timestamp_inicio).total_seconds() * 1000),
                status=StageStatus.SUCCESS,
                verificacion=verificacion,
                data={"proveedor_info": proveedor}
            )
            self.execution_logger.add_stage_result(stage_result)

            if verificacion.resultado == VerificationResult.FAIL and self.exit_on_failure:
                raise StageFailure(f"Verificación proveedor fallida: {verificacion.mensaje}")

            return proveedor

        except StageFailure:
            raise
        except Exception as e:
            self._registrar_etapa_error(etapa_num, nombre, descripcion, timestamp_inicio, str(e))
            raise StageFailure(f"Error en validación proveedor: {e}")

    def _ejecutar_etapa_oc(self, datos_factura: dict, proveedor_info: dict) -> list:
        """Ejecuta la etapa de búsqueda de OC."""
        etapa_num = 4
        nombre, descripcion = self.ETAPAS[etapa_num]
        timestamp_inicio = datetime.now()

        print(f"\n{'='*70}")
        print(f"ETAPA {etapa_num}: {descripcion.upper()}")
        print(f"{'='*70}")

        try:
            supplier_code = proveedor_info.get('Supplier', '')
            tax_code = datos_factura.get('TaxCode', 'V0')

            print(f"  Proveedor SAP: {supplier_code}")
            print(f"  Monto: {datos_factura.get('InvoiceGrossAmount', 0.0)}")

            # Nueva llamada con selección determinística
            resultado = obtener_ordenes_compra(supplier_code, datos_factura, tax_code)

            if resultado.get("status") == "duplicate_requires_intervention":
                candidatos = resultado.get('candidatos', [])
                msg = "Múltiples OCs con score similar:\n"
                for i, cand in enumerate(candidatos[:3]):
                    msg += f"  {i+1}. OC {cand.get('selected_purchase_order')} - Score: {cand.get('match_score', 0):.1f}\n"
                raise StageFailure(msg)
            elif resultado.get("status") == "not_found":
                raise StageFailure(f"OCs no encontradas: {resultado.get('error')}")
            elif resultado.get("status") == "error":
                raise StageFailure(f"Error en búsqueda OC: {resultado.get('error')}")

            # Extraer datos de la selección determinística
            oc_data = resultado["data"]
            oc_items = oc_data.get('oc_items', [])
            needs_migo = oc_data.get('needs_migo', False)
            match_score = oc_data.get('match_score', 0)
            print(f"  OC Seleccionada: {oc_data.get('selected_purchase_order')}")
            print(f"  Item: {oc_data.get('selected_purchase_order_item')}")
            print(f"  Score: {match_score:.1f}/100")
            print(f"  Requiere MIGO: {'Sí' if needs_migo else 'No'}")
            for oc in oc_items:
                print(f"    - OC: {oc.get('PurchaseOrder')} Item: {oc.get('PurchaseOrderItem')}")

            # Verificar OC
            verificacion = self.verifier.verify_ordenes_compra(oc_items)
            self._print_verification(verificacion)

            # Registrar etapa
            stage_result = StageResult(
                etapa=etapa_num,
                nombre=nombre,
                descripcion=descripcion,
                timestamp_inicio=timestamp_inicio,
                timestamp_fin=datetime.now(),
                duracion_ms=int((datetime.now() - timestamp_inicio).total_seconds() * 1000),
                status=StageStatus.SUCCESS,
                verificacion=verificacion,
                data={
                    "oc_items": oc_items,
                    "needs_migo": needs_migo,
                    "match_score": match_score,
                    "selected_purchase_order": oc_data.get('selected_purchase_order'),
                    "selected_purchase_order_item": oc_data.get('selected_purchase_order_item')
                }
            )
            self.execution_logger.add_stage_result(stage_result)

            if verificacion.resultado == VerificationResult.FAIL and self.exit_on_failure:
                raise StageFailure(f"Verificación OC fallida: {verificacion.mensaje}")

            # Retornar dict con toda la info necesaria
            return {
                "oc_items": oc_items,
                "needs_migo": needs_migo,
                "match_score": match_score,
                "selected_purchase_order": oc_data.get('selected_purchase_order'),
                "selected_purchase_order_item": oc_data.get('selected_purchase_order_item')
            }

        except StageFailure:
            raise
        except Exception as e:
            self._registrar_etapa_error(etapa_num, nombre, descripcion, timestamp_inicio, str(e))
            raise StageFailure(f"Error en búsqueda OC: {e}")

    def _ejecutar_etapa_migo(self, datos_factura: dict, oc_data: dict) -> dict:
        """
        Ejecuta la etapa de verificación de entrada de material (MIGO).

        OBLIGATORIA: Si no hay MIGO válido, el proceso se detiene.
        No se puede facturar un producto que no ha llegado a almacén.
        """
        etapa_num = 5
        nombre, descripcion = self.ETAPAS[etapa_num]
        timestamp_inicio = datetime.now()

        print(f"\n{'='*70}")
        print(f"ETAPA {etapa_num}: {descripcion.upper()} - OBLIGATORIA")
        print(f"{'='*70}")

        try:
            # Extraer datos de la OC seleccionada
            purchase_order = oc_data.get('selected_purchase_order', '')
            purchase_order_item = oc_data.get('selected_purchase_order_item', '')
            oc_items = oc_data.get('oc_items', [])

            if not purchase_order:
                raise StageFailure("No hay OC seleccionada para verificar MIGO")

            # Preparar oc_info con material
            oc_info = {}
            if oc_items:
                oc_info = {
                    "PurchaseOrder": purchase_order,
                    "PurchaseOrderItem": purchase_order_item,
                    "Material": oc_items[0].get("Material", "")
                }
            else:
                oc_info = {
                    "PurchaseOrder": purchase_order,
                    "PurchaseOrderItem": purchase_order_item
                }

            print(f"  Verificando MIGO para OC: {purchase_order}")
            print(f"  Item OC: {purchase_order_item}")
            if oc_info.get("Material"):
                print(f"  Material: {oc_info.get('Material')}")

            resultado = verificar_entrada_material(
                purchase_order,
                purchase_order_item,
                datos_factura,
                oc_info
            )

            # MIGO es OBLIGATORIO - si no se encuentra, detener el proceso
            if resultado.get("status") == "not_found":
                error_msg = f"No se encontraron entradas de material (MIGO) para OC {purchase_order}"
                print(f"  ❌ {error_msg}")
                print(f"  ⛔ No se puede facturar un producto que no ha llegado a almacén.")
                self._registrar_etapa_error(etapa_num, nombre, descripcion, timestamp_inicio, error_msg)
                raise StageFailure(error_msg)

            if resultado.get("status") == "error":
                error_msg = resultado.get('error', 'Error desconocido en verificación MIGO')
                print(f"  ❌ Error en verificación: {error_msg}")
                raise StageFailure(f"Error en verificación MIGO: {error_msg}")

            # MIGO encontrado exitosamente
            migo_data = resultado["data"]
            reference_document = migo_data.get("reference_document", {})
            match_score = migo_data.get("match_score", 0)
            cantidad_disponible = migo_data.get("cantidad_disponible", 0)
            cantidad_factura = migo_data.get("cantidad_factura", 0)
            estado_cantidad = migo_data.get("estado_cantidad", "")

            print(f"\n  ✅ MIGO VERIFICADO CORRECTAMENTE")
            print(f"     • Score: {match_score:.1f}/100")
            print(f"     • Cantidad disponible: {cantidad_disponible}")
            print(f"     • Cantidad factura: {cantidad_factura}")
            print(f"     • Estado: {estado_cantidad}")
            print(f"     • ReferenceDocument: {reference_document.get('ReferenceDocument', 'N/A')}")
            print(f"     • Año fiscal: {reference_document.get('ReferenceDocumentFiscalYear', 'N/A')}")
            print(f"     • Item: {reference_document.get('ReferenceDocumentItem', 'N/A')}")

            # Preparar resultado para el flujo
            migo_result = {
                "status": "success",
                "purchase_order": purchase_order,
                "reference_document": reference_document,
                "match_score": match_score,
                "cantidad_disponible": cantidad_disponible,
                "cantidad_factura": cantidad_factura,
                "estado_cantidad": estado_cantidad
            }

            # Registrar etapa exitosa
            stage_result = StageResult(
                etapa=etapa_num,
                nombre=nombre,
                descripcion=descripcion,
                timestamp_inicio=timestamp_inicio,
                timestamp_fin=datetime.now(),
                duracion_ms=int((datetime.now() - timestamp_inicio).total_seconds() * 1000),
                status=StageStatus.SUCCESS,
                data={"migo_result": migo_result}
            )
            self.execution_logger.add_stage_result(stage_result)

            return migo_result

        except StageFailure:
            raise
        except Exception as e:
            self._registrar_etapa_error(etapa_num, nombre, descripcion, timestamp_inicio, str(e))
            raise StageFailure(f"Error en verificación MIGO: {e}")

    def _ejecutar_etapa_json(
        self,
        datos_factura: dict,
        proveedor_info: dict,
        oc_items: list,
        needs_migo: bool = False,
        reference_document: dict = None
    ) -> dict:
        """Ejecuta la etapa de construcción de JSON."""
        etapa_num = 6
        nombre, descripcion = self.ETAPAS[etapa_num]
        timestamp_inicio = datetime.now()

        print(f"\n{'='*70}")
        print(f"ETAPA {etapa_num}: {descripcion.upper()}")
        print(f"{'='*70}")

        try:
            resultado = construir_json_factura(
                datos_factura,
                proveedor_info,
                oc_items,
                needs_migo=needs_migo,
                reference_document=reference_document
            )

            if resultado.get("status") != "success":
                raise StageFailure(f"Error construyendo JSON: {resultado.get('error')}")

            factura_json = resultado["data"]
            print(f"  JSON construido correctamente")
            print(f"  Preview:")
            print(json.dumps(factura_json, indent=2, ensure_ascii=False)[:500] + "...")

            # Verificar JSON
            verificacion = self.verifier.verify_json_sap(factura_json)
            self._print_verification(verificacion)

            # Registrar etapa
            stage_result = StageResult(
                etapa=etapa_num,
                nombre=nombre,
                descripcion=descripcion,
                timestamp_inicio=timestamp_inicio,
                timestamp_fin=datetime.now(),
                duracion_ms=int((datetime.now() - timestamp_inicio).total_seconds() * 1000),
                status=StageStatus.SUCCESS,
                verificacion=verificacion,
                data={"factura_json": factura_json}
            )
            self.execution_logger.add_stage_result(stage_result)

            if verificacion.resultado == VerificationResult.FAIL and self.exit_on_failure:
                raise StageFailure(f"Verificación JSON fallida: {verificacion.mensaje}")

            return factura_json

        except StageFailure:
            raise
        except Exception as e:
            self._registrar_etapa_error(etapa_num, nombre, descripcion, timestamp_inicio, str(e))
            raise StageFailure(f"Error en construcción JSON: {e}")

    def _ejecutar_etapa_envio(self, factura_json: dict) -> dict:
        """Ejecuta la etapa de envío a SAP."""
        etapa_num = 7
        nombre, descripcion = self.ETAPAS[etapa_num]
        timestamp_inicio = datetime.now()

        print(f"\n{'='*70}")
        print(f"ETAPA {etapa_num}: {descripcion.upper()}")
        print(f"{'='*70}")

        try:
            print("  Enviando factura a SAP...")
            resultado = enviar_factura_sap(factura_json)

            if resultado.get("status") != "success":
                raise StageFailure(f"Error enviando a SAP: {resultado.get('error')}")

            respuesta = resultado["data"]
            print("  Factura enviada exitosamente!")

            # Registrar etapa (sin verificación específica para envío)
            stage_result = StageResult(
                etapa=etapa_num,
                nombre=nombre,
                descripcion=descripcion,
                timestamp_inicio=timestamp_inicio,
                timestamp_fin=datetime.now(),
                duracion_ms=int((datetime.now() - timestamp_inicio).total_seconds() * 1000),
                status=StageStatus.SUCCESS,
                data={"respuesta_sap": respuesta}
            )
            self.execution_logger.add_stage_result(stage_result)

            return respuesta

        except StageFailure:
            raise
        except Exception as e:
            self._registrar_etapa_error(etapa_num, nombre, descripcion, timestamp_inicio, str(e))
            raise StageFailure(f"Error en envío SAP: {e}")

    def _registrar_etapa_error(
        self,
        etapa_num: int,
        nombre: str,
        descripcion: str,
        timestamp_inicio: datetime,
        error: str
    ):
        """Registra una etapa con error."""
        stage_result = StageResult(
            etapa=etapa_num,
            nombre=nombre,
            descripcion=descripcion,
            timestamp_inicio=timestamp_inicio,
            timestamp_fin=datetime.now(),
            duracion_ms=int((datetime.now() - timestamp_inicio).total_seconds() * 1000),
            status=StageStatus.ERROR,
            error=error
        )
        self.execution_logger.add_stage_result(stage_result)

    def _registrar_etapa_skip(self, etapa_num: int, mensaje: str):
        """Registra una etapa omitida."""
        nombre, descripcion = self.ETAPAS[etapa_num]
        stage_result = StageResult(
            etapa=etapa_num,
            nombre=nombre,
            descripcion=descripcion,
            timestamp_inicio=datetime.now(),
            timestamp_fin=datetime.now(),
            duracion_ms=0,
            status=StageStatus.SKIPPED,
            data={"mensaje": mensaje}
        )
        self.execution_logger.add_stage_result(stage_result)
        print(f"\n  [ETAPA {etapa_num}] {mensaje}")

    def _print_verification(self, verificacion):
        """Imprime resultado de verificación."""
        if not verificacion.ejecutada:
            print(f"  [VERIFICACION] No ejecutada - {verificacion.mensaje}")
            return

        simbolo = {
            VerificationResult.PASS: "PASS",
            VerificationResult.WARNING: "WARN",
            VerificationResult.FAIL: "FAIL",
        }.get(verificacion.resultado, "?")

        print(f"  [VERIFICACION] [{simbolo}] {verificacion.mensaje}")

        if verificacion.detalles and verificacion.resultado != VerificationResult.PASS:
            for key, value in verificacion.detalles.items():
                if isinstance(value, dict):
                    print(f"    - {key}:")
                    for k, v in value.items():
                        print(f"        {k}: {v}")
                elif isinstance(value, list) and len(value) > 0:
                    print(f"    - {key}: {value}")

    def _check_exit(self, etapa_completada: int):
        """Verifica si debe terminar después de una etapa."""
        if self.exit_after_stage and etapa_completada >= self.exit_after_stage:
            print(f"\n[DEV] Terminando después de etapa {etapa_completada} (configurado con --exit-after)")
            log_path = self.execution_logger.finish_execution(ExecutionResult.PARTIAL)
            print(f"[LOG] Guardado en: {log_path}")
            sys.exit(0)


def main():
    """Punto de entrada principal."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Flujo de facturas con verificación por etapas",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Solo verificar OCR (etapa 1)
  python -m scripts.flujo_completo_verificado factura.pdf --exit-after 1

  # Verificar hasta parsing (etapa 2)
  python -m scripts.flujo_completo_verificado factura.pdf --exit-after 2

  # Flujo completo sin enviar a SAP
  python -m scripts.flujo_completo_verificado factura.pdf

  # Flujo completo enviando a SAP
  python -m scripts.flujo_completo_verificado factura.pdf --enviar
        """
    )
    parser.add_argument("pdf_path", help="Ruta al PDF de factura")
    parser.add_argument("--enviar", "-e", action="store_true", help="Enviar a SAP")
    parser.add_argument("--no-comparar-ocr", action="store_true", help="No comparar OCRs")
    parser.add_argument("--no-exit-on-fail", action="store_true", help="Continuar aunque falle verificación")
    parser.add_argument("--exit-after", type=int, choices=[1, 2, 3, 4, 5, 6, 7], help="Terminar después de etapa N")
    parser.add_argument("--ground-truth", help="Ruta a archivo de ground truth")

    args = parser.parse_args()

    flujo = FlujoVerificado(
        ground_truth_path=args.ground_truth,
        comparar_ocr=not args.no_comparar_ocr,
        exit_on_failure=not args.no_exit_on_fail,
        exit_after_stage=args.exit_after,
    )

    resultado = flujo.ejecutar(args.pdf_path, enviar=args.enviar)

    # Resumen final
    print("\n" + "=" * 70)
    print("RESUMEN FINAL")
    print("=" * 70)
    if resultado.get("success"):
        print("  Resultado: EXITO")
        print("  Número de factura:", resultado.get("d", {}).get("SupplierInvoice", "N/A"))
    else:
        print(f"  Resultado: ERROR - {resultado.get('error', 'Desconocido')}")
    print(f"  Log: {resultado.get('log_path', 'N/A')}")
    print("=" * 70)

    sys.exit(0 if resultado.get("success") else 1)


if __name__ == "__main__":
    main()

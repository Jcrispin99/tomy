"""
Empaquetador de archivos .img de Vieworks VXvue.

La plantilla aporta el header binario (56 bytes), el separador interno
entre bloques de pixeles y la zona desconocida que va antes del XML.
Los dos bloques de pixeles se sobreescriben con la imagen renderizada
desde el PDF y el XML se reemplaza por uno nuevo con los datos del
paciente/estudio.

Uso desde otro modulo:
    from scripts_img.empaquetar_img import empaquetar_img, pdf_a_pixeles
    pixeles = pdf_a_pixeles(Path("estudio.pdf"))
    empaquetar_img(salida, paciente, estudio, pixeles)

Uso CLI:
    python -m scripts_img.empaquetar_img <entrada.pdf> <salida.img>
"""
from __future__ import annotations

import struct
import sys
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import io

import fitz  # pymupdf
import numpy as np
from PIL import Image


PLANTILLA = Path(__file__).resolve().parent / "plantilla_vacia.img"
FIRMA_XML_UTF16 = "<?xml".encode("utf-16-le")

ANCHO = ALTO = 3072
BITS = 14
PX_MAX = (1 << BITS) - 1  # 16383
BLOQUE_PX_BYTES = ANCHO * ALTO * 2  # 18,874,368
OFFSET_PUNTERO_XML = 0x24  # uint32 LE con (xml_pos - 4)


@dataclass
class DatosPaciente:
    code: str                         # "0000001"
    last_name: str = ""
    first_name: str = ""
    sex: str = ""                     # "M" o "F" (vacio si no se conoce)
    age: int | None = None            # anios; None deja vacio
    birth_date: str = ""              # YYYYMMDD


@dataclass
class DatosEstudio:
    study_uid: str
    series_uid: str
    instance_uid: str
    body_part: str = ""               # ej. "ABDOMEN"
    study_date: str = ""              # YYYYMMDD
    study_time: str = ""              # HHMMSS
    accession_number: str = ""
    performing_physician: str = ""
    institution: str = ""


def generar_uid(prefix: str = "2.25.") -> str:
    """Genera un UID DICOM unico usando un UUID4 convertido a entero.

    El OID 2.25 esta reservado por DICOM para UUIDs derivados.
    Maximo 64 caracteres por norma DICOM.
    """
    cuerpo = str(uuid.uuid4().int)
    return (prefix + cuerpo)[:64]


def _localizar_xml(data: bytes) -> int:
    pos = data.find(FIRMA_XML_UTF16)
    if pos < 0:
        raise ValueError("La plantilla no contiene un bloque XML UTF-16 LE.")
    return pos


def _nombre_dicom(last_name: str, first_name: str) -> str:
    return f"{last_name.strip()}^{first_name.strip()}^^^"


def _aplicar_datos_al_xml(
    xml_texto: str,
    paciente: DatosPaciente,
    estudio: DatosEstudio,
) -> str:
    root = ET.fromstring(xml_texto)

    def set_attrs(path: str, valores: dict) -> None:
        nodo = root.find(path)
        if nodo is None:
            return
        for k, v in valores.items():
            nodo.set(k, v)

    edad_str = f"{paciente.age:03d}Y" if paciente.age is not None else ""

    set_attrs("PATIENT_INFO/Patient", {
        "ID": paciente.code,
        "Name": _nombre_dicom(paciente.last_name, paciente.first_name),
        "BirthDate": paciente.birth_date,
        "Sex": paciente.sex,
    })

    set_attrs("STUDY_INFO/Study", {
        "Date": estudio.study_date,
        "Time": estudio.study_time,
        "InstanceUID": estudio.study_uid,
        "AccessionNumber": estudio.accession_number,
        "PerformingPhysicianName": estudio.performing_physician,
    })
    set_attrs("STUDY_INFO/Patient", {"Age": edad_str})
    set_attrs("STUDY_INFO/Scheduled", {
        "ProcedureStepStartDate": estudio.study_date,
        "PerformingPhysicianName": estudio.performing_physician,
    })
    set_attrs("STUDY_INFO/Institution", {"Name": estudio.institution})

    set_attrs("SERIES_INFO/Series", {
        "Date": estudio.study_date,
        "Time": estudio.study_time,
        "ProtocolName": estudio.body_part,
        "BodypartExamined": estudio.body_part,
        "InstanceUID": estudio.series_uid,
    })
    set_attrs("SERIES_INFO/PerformedProcedureStep", {
        "StartDate": estudio.study_date,
        "StartTime": estudio.study_time,
    })
    fisico = root.find("SERIES_INFO/PerformingPhysician/Physician")
    if fisico is not None:
        fisico.set("Name", estudio.performing_physician)

    set_attrs("INSTANCE_INFO/Instance", {
        "ContentDate": estudio.study_date,
        "ContentTime": estudio.study_time,
        "AcquisitionDate": estudio.study_date,
        "AcquisitionTime": estudio.study_time,
        "InstanceUID": estudio.instance_uid,
        "ImageID": "",
    })

    # Vaciar datos de dosis: los valores eran reales del estudio original
    # y arrastrarlos a un .img nuevo seria informacion clinica falsa.
    set_attrs("INSTANCE_INFO/Dose", {
        "KVP": "", "MA": "", "MS": "", "MAS": "",
        "ExposureIndex": "", "TargetExposureIndex": "",
        "DeviationIndex": "", "Dap": "",
    })

    cuerpo = ET.tostring(root, encoding="unicode").replace(" />", "/>")
    return '<?xml version="1.0"?>\r\n' + cuerpo + '\r\n'


def _extraer_imagen_pdf(pdf_path: Path) -> Image.Image:
    """Devuelve la imagen mas grande embebida en la primera pagina.
    Si no hay imagenes embebidas, rasteriza la pagina a alta resolucion.
    """
    with fitz.open(pdf_path) as doc:
        page = doc[0]
        imagenes = page.get_images(full=True)
        if imagenes:
            # Tomar la de mayor area (descarta logos pequenos)
            mejor_xref = max(imagenes, key=lambda im: doc.extract_image(im[0])['width']
                             * doc.extract_image(im[0])['height'])[0]
            info = doc.extract_image(mejor_xref)
            return Image.open(io.BytesIO(info['image']))

        # Fallback: rasterizar a 4x para tener resolucion decente
        zoom = max(ANCHO * 2 / page.rect.width, ALTO * 2 / page.rect.height)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        return Image.frombytes('RGB', (pix.width, pix.height), pix.samples)


def pdf_a_pixeles(pdf_path: Path) -> np.ndarray:
    """Convierte la primera pagina del PDF a una matriz uint16 3072x3072
    de 14 bits, lista para empaquetar en un .img Vieworks.

    Pasa el JPEG embebido tal cual: gris, resize LANCZOS preservando aspect,
    padding blanco para integrarse con el fondo del escaneo. Sin inversion
    ni ajustes de contraste; el visor aplica su propio window/level.
    """
    img = _extraer_imagen_pdf(pdf_path)
    if img.mode != 'L':
        img = img.convert('L')
    gris = np.array(img, dtype=np.uint8)

    h, w = gris.shape
    escala = min(ALTO / h, ANCHO / w)
    nuevo_h, nuevo_w = max(1, round(h * escala)), max(1, round(w * escala))
    if (h, w) != (nuevo_h, nuevo_w):
        gris = np.array(
            Image.fromarray(gris).resize((nuevo_w, nuevo_h), Image.LANCZOS),
            dtype=np.uint8,
        )

    # Padding blanco: continua el fondo del papel escaneado y deja la
    # radiografia tal cual la decidio el origen, sin transformar colores.
    lienzo = np.full((ALTO, ANCHO), 255, dtype=np.uint8)
    y0 = (ALTO - gris.shape[0]) // 2
    x0 = (ANCHO - gris.shape[1]) // 2
    lienzo[y0:y0 + gris.shape[0], x0:x0 + gris.shape[1]] = gris

    return (lienzo.astype(np.uint32) * PX_MAX // 255).astype(np.uint16)


def empaquetar_img(
    salida: Path,
    paciente: DatosPaciente,
    estudio: DatosEstudio,
    pixeles: np.ndarray,
    plantilla: Path = PLANTILLA,
) -> Path:
    """Genera un .img nuevo escribiendo:
      - header binario y zona intermedia copiados de `plantilla`
      - ambos bloques de pixeles sobreescritos con `pixeles` (3072x3072 uint16)
      - puntero al XML en offset 0x24 actualizado
      - XML reemplazado con los datos provistos
    """
    if pixeles.shape != (ALTO, ANCHO) or pixeles.dtype != np.uint16:
        raise ValueError(
            f"pixeles debe ser uint16 {ALTO}x{ANCHO}, "
            f"recibido {pixeles.dtype} {pixeles.shape}"
        )

    salida = Path(salida)
    plantilla = Path(plantilla)
    data = bytearray(plantilla.read_bytes())
    xml_inicio = _localizar_xml(data)

    px_bytes = pixeles.tobytes()
    # Bloque 1: empieza justo despues del header (0x38)
    fin_bloque1 = 0x38 + BLOQUE_PX_BYTES
    data[0x38:fin_bloque1] = px_bytes
    # Separador de 8 bytes entre bloques, despues empieza bloque 2
    inicio_bloque2 = fin_bloque1 + 8
    fin_bloque2 = inicio_bloque2 + BLOQUE_PX_BYTES
    data[inicio_bloque2:fin_bloque2] = px_bytes

    # XML nuevo
    xml_texto = bytes(data[xml_inicio:]).decode("utf-16-le", errors="replace")
    nuevo_xml = _aplicar_datos_al_xml(xml_texto, paciente, estudio)
    nuevo_xml_bytes = nuevo_xml.encode("utf-16-le")

    # Pre-XML (header + bloques + zona intermedia) conserva su tamano,
    # pero el XML puede haber cambiado de longitud: el puntero apunta a
    # (nuevo_xml_pos - 4).
    nuevo_xml_pos = xml_inicio
    struct.pack_into("<I", data, OFFSET_PUNTERO_XML, nuevo_xml_pos - 4)

    salida.parent.mkdir(parents=True, exist_ok=True)
    with open(salida, "wb") as f:
        f.write(data[:xml_inicio])
        f.write(nuevo_xml_bytes)
    return salida


def _main_cli() -> None:
    if len(sys.argv) < 3:
        print("Uso: python -m scripts_img.empaquetar_img "
              "<entrada.pdf> <salida.img>")
        sys.exit(1)

    pdf_path = Path(sys.argv[1])
    salida = Path(sys.argv[2])

    paciente = DatosPaciente(
        code="0000099",
        last_name="PRUEBA",
        first_name="DE PRUEBA",
        sex="M",
        age=30,
    )
    estudio = DatosEstudio(
        study_uid=generar_uid(),
        series_uid=generar_uid(),
        instance_uid=generar_uid(),
        body_part="ABDOMEN",
        study_date="20260624",
        study_time="100000",
        performing_physician="rayosx^^^^",
        institution="CENTRO MEDICO TINTAYA",
    )
    pixeles = pdf_a_pixeles(pdf_path)
    ruta = empaquetar_img(salida, paciente, estudio, pixeles)
    print(f"Generado: {ruta}")


if __name__ == "__main__":
    _main_cli()

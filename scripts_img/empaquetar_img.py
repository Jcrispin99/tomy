"""
Empaquetador de archivos .img de Vieworks VXvue.

Fase 1: reutiliza los pixeles de una plantilla .img existente y solo
reemplaza el bloque XML de metadatos al final del archivo con los datos
nuevos del paciente/estudio.

Uso desde otro modulo:
    from scripts_img.empaquetar_img import empaquetar_img
    empaquetar_img(plantilla, salida, datos)

Uso CLI:
    python -m scripts_img.empaquetar_img <plantilla.img> <salida.img>
"""
from __future__ import annotations

import sys
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


PLANTILLA_DEFECTO = Path(__file__).resolve().parent.parent / "S2695I3233.img"
FIRMA_XML_UTF16 = "<?xml".encode("utf-16-le")


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
    })

    cuerpo = ET.tostring(root, encoding="unicode").replace(" />", "/>")
    return '<?xml version="1.0"?>\r\n' + cuerpo + '\r\n'


def empaquetar_img(
    salida: Path,
    paciente: DatosPaciente,
    estudio: DatosEstudio,
    plantilla: Path = PLANTILLA_DEFECTO,
) -> Path:
    """Genera un .img nuevo en `salida` reusando los pixeles de `plantilla`
    y reemplazando el XML con los datos provistos.
    """
    salida = Path(salida)
    plantilla = Path(plantilla)
    data = plantilla.read_bytes()
    xml_inicio = _localizar_xml(data)
    xml_texto = data[xml_inicio:].decode("utf-16-le", errors="replace")

    nuevo_xml = _aplicar_datos_al_xml(xml_texto, paciente, estudio)
    nuevo_xml_bytes = nuevo_xml.encode("utf-16-le")

    salida.parent.mkdir(parents=True, exist_ok=True)
    with open(salida, "wb") as f:
        f.write(data[:xml_inicio])
        f.write(nuevo_xml_bytes)
    return salida


def _main_cli() -> None:
    if len(sys.argv) < 3:
        print("Uso: python -m scripts_img.empaquetar_img "
              "<plantilla.img> <salida.img>")
        sys.exit(1)

    plantilla = Path(sys.argv[1])
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
    ruta = empaquetar_img(salida, paciente, estudio, plantilla)
    print(f"Generado: {ruta}")


if __name__ == "__main__":
    _main_cli()

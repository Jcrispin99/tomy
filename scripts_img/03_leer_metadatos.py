"""
Parser de metadatos para archivos .img de Vieworks VXvue.

Estructura del archivo:
  - Bytes 0..256       : cabecera fija (...CH1...IMG...)
  - Bytes 256..XML_off : pixeles crudos (Width x Height x ceil(UsingBits/8))
  - Bytes XML_off..fin : metadatos en XML codificado en UTF-16 LE

Este script solo lee. No modifica nada.
"""
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


FIRMA_XML_UTF16 = "<?xml".encode("utf-16-le")


def localizar_xml(data: bytes) -> tuple[int, int]:
    """Devuelve (offset_inicio, offset_fin_exclusivo) del bloque XML UTF-16LE."""
    inicio = data.find(FIRMA_XML_UTF16)
    if inicio < 0:
        raise ValueError("No se encontro firma '<?xml' en UTF-16 LE.")

    fin = inicio
    while fin < len(data) - 1:
        b0, b1 = data[fin], data[fin + 1]
        if b1 != 0x00 or not (0x09 <= b0 <= 0x7e):
            break
        fin += 2
    return inicio, fin


def leer_xml(ruta: Path) -> tuple[str, int, int]:
    """Devuelve (texto_xml, xml_inicio, xml_fin)."""
    data = ruta.read_bytes()
    inicio, fin = localizar_xml(data)
    texto = data[inicio:fin].decode("utf-16-le", errors="replace")
    return texto, inicio, fin


def extraer_resumen(xml_texto: str) -> dict:
    """Saca los campos mas utiles del XML a un dict plano."""
    root = ET.fromstring(xml_texto)

    def attrs_de(path: str) -> dict:
        nodo = root.find(path)
        return dict(nodo.attrib) if nodo is not None else {}

    paciente = attrs_de("PATIENT_INFO/Patient")
    estudio = attrs_de("STUDY_INFO/Study")
    estudio_pac = attrs_de("STUDY_INFO/Patient")
    institucion = attrs_de("STUDY_INFO/Institution")
    serie = attrs_de("SERIES_INFO/Series")
    instancia = attrs_de("INSTANCE_INFO/Instance")
    detector = attrs_de("INSTANCE_INFO/Detector")
    dosis = attrs_de("INSTANCE_INFO/Dose")
    pixel_spacing = attrs_de("INSTANCE_INFO/PixelSpacing")
    anatomia = root.find("INSTANCE_INFO/Anatomic/CodeSequence")
    anatomia_attrs = dict(anatomia.attrib) if anatomia is not None else {}

    nombre_raw = paciente.get("Name", "")
    apellidos_nombres = nombre_raw.split("^")
    nombre_legible = (f"{apellidos_nombres[1].strip()} "
                      f"{apellidos_nombres[0].strip()}").strip() \
        if len(apellidos_nombres) >= 2 else nombre_raw

    return {
        "paciente": {
            "id": paciente.get("ID"),
            "nombre_dicom": nombre_raw,
            "nombre_legible": nombre_legible,
            "fecha_nacimiento": paciente.get("BirthDate"),
            "sexo": paciente.get("Sex"),
            "edad": estudio_pac.get("Age"),
        },
        "institucion": institucion.get("Name"),
        "estudio": {
            "fecha": estudio.get("Date"),
            "hora": estudio.get("Time"),
            "modalidad": serie.get("Modality"),
            "parte_examinada": serie.get("BodypartExamined"),
            "protocolo": serie.get("ProtocolName"),
            "medico_realiza": estudio.get("PerformingPhysicianName"),
            "uid_estudio": estudio.get("InstanceUID"),
            "uid_serie": serie.get("InstanceUID"),
            "uid_instancia": instancia.get("InstanceUID"),
            "anatomia_codigo": anatomia_attrs.get("Code"),
            "anatomia_descripcion": anatomia_attrs.get("Mesning"),
        },
        "imagen": {
            "ancho": int(instancia.get("Width", 0)),
            "alto": int(instancia.get("Height", 0)),
            "bits": int(instancia.get("UsingBits", 0)),
            "pixel_spacing_mm": (pixel_spacing.get("Value1"),
                                 pixel_spacing.get("Value2")),
        },
        "detector": {
            "fabricante": detector.get("ManufacturerName"),
            "modelo": detector.get("ManufacturerModelName"),
            "serie": detector.get("DetectorSerial"),
        },
        "tecnica": {
            "kvp": dosis.get("KVP"),
            "mA": dosis.get("MA"),
            "ms": dosis.get("MS"),
            "mAs": dosis.get("MAS"),
            "exposure_index": dosis.get("ExposureIndex"),
        },
    }


def main():
    if len(sys.argv) >= 2:
        ruta = Path(sys.argv[1])
    else:
        ruta = Path(__file__).resolve().parent.parent / "S2695I3233.img"

    if not ruta.exists():
        print(f"No existe el archivo: {ruta}")
        sys.exit(1)

    xml_texto, xml_inicio, xml_fin = leer_xml(ruta)
    tamano = ruta.stat().st_size

    print(f"Archivo:        {ruta.name}")
    print(f"Tamano total:   {tamano:,} bytes")
    print(f"Bloque pixeles: bytes 256 .. {xml_inicio:,} "
          f"(~{(xml_inicio - 256) / (1024 * 1024):.2f} MB)")
    print(f"Bloque XML:     bytes {xml_inicio:,} .. {xml_fin:,} "
          f"({xml_fin - xml_inicio:,} bytes UTF-16LE)\n")

    resumen = extraer_resumen(xml_texto)
    print("METADATOS EXTRAIDOS")
    print("=" * 60)
    print(json.dumps(resumen, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

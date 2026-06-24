"""
Extrae el bloque XML de metadatos del .img y lo imprime/guarda.
"""
import re
from pathlib import Path

RUTA = Path(__file__).resolve().parent / "plantilla_vacia.img"
SALIDA_XML = Path(__file__).resolve().parent / "metadatos_extraidos.xml"


def extraer_xml_utf16(data: bytes) -> tuple[int, int, str] | None:
    """Busca un bloque UTF-16 LE que contenga el XML de metadatos.

    Devuelve (offset_inicio, offset_fin_exclusivo, texto).
    """
    firma = "<?xml".encode("utf-16-le")
    inicio = data.find(firma)
    if inicio < 0:
        return None

    # Avanzamos byte por byte de 2 en 2 mientras siga siendo UTF-16 imprimible
    fin = inicio
    while fin < len(data) - 1:
        b0, b1 = data[fin], data[fin + 1]
        if b1 != 0x00:
            break
        if not (0x09 <= b0 <= 0x7e):
            break
        fin += 2

    texto = data[inicio:fin].decode("utf-16-le", errors="replace")
    return inicio, fin, texto


def main():
    data = RUTA.read_bytes()
    print(f"Archivo: {RUTA.name}   Tamano: {len(data):,} bytes\n")

    resultado = extraer_xml_utf16(data)
    if resultado is None:
        print("No se encontro firma XML en UTF-16 LE.")
        return

    inicio, fin, texto = resultado
    print(f"Bloque XML detectado:")
    print(f"  offset inicio: {inicio} (0x{inicio:x})")
    print(f"  offset fin:    {fin} (0x{fin:x})")
    print(f"  bytes:         {fin - inicio}")
    print(f"  caracteres:    {(fin - inicio) // 2}\n")

    print("Antes del XML hay un bloque binario que probablemente es la imagen.")
    print(f"  Tamano del bloque previo (sospechado pixeles + cabecera): "
          f"{inicio:,} bytes ({inicio / (1024 * 1024):.2f} MB)\n")

    SALIDA_XML.write_text(texto, encoding="utf-8")
    print(f"XML guardado en: {SALIDA_XML}\n")

    # Vista previa formateada
    print("=" * 70)
    print("CONTENIDO XML EXTRAIDO:")
    print("=" * 70)
    print(texto[:8000])
    if len(texto) > 8000:
        print(f"\n... ({len(texto) - 8000} caracteres mas)")


if __name__ == "__main__":
    main()

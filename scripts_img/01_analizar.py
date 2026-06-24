"""
Analisis forense del archivo .img para descubrir donde estan los metadatos.
No modifica nada. Solo lee y reporta.
"""
import os
import re
import sys
from pathlib import Path

RUTA = Path(__file__).resolve().parent / "plantilla_vacia.img"


def hexdump_seccion(data: bytes, inicio: int, largo: int = 256) -> str:
    """Muestra un bloque en hex + ascii."""
    bloque = data[inicio:inicio + largo]
    salida = []
    for i in range(0, len(bloque), 16):
        chunk = bloque[i:i + 16]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        salida.append(f"{inicio + i:08x}  {hex_part:<48s}  {ascii_part}")
    return "\n".join(salida)


def buscar_strings_ascii(data: bytes, min_largo: int = 6) -> list[tuple[int, str]]:
    """Encuentra cadenas ASCII imprimibles."""
    patron = re.compile(rb"[\x20-\x7e]{%d,}" % min_largo)
    return [(m.start(), m.group().decode("ascii", "ignore")) for m in patron.finditer(data)]


def buscar_strings_utf16le(data: bytes, min_largo: int = 6) -> list[tuple[int, str]]:
    """Encuentra cadenas en UTF-16 Little Endian (texto + 0x00 alternado)."""
    resultados = []
    i = 0
    while i < len(data) - min_largo * 2:
        if 0x20 <= data[i] <= 0x7e and data[i + 1] == 0x00:
            j = i
            while j < len(data) - 1 and 0x20 <= data[j] <= 0x7e and data[j + 1] == 0x00:
                j += 2
            largo_caracteres = (j - i) // 2
            if largo_caracteres >= min_largo:
                try:
                    texto = data[i:j].decode("utf-16-le")
                    resultados.append((i, texto))
                except UnicodeDecodeError:
                    pass
            i = j + 2
        else:
            i += 1
    return resultados


def buscar_firma_dicom(data: bytes) -> int | None:
    """DICOM tiene 'DICM' en el offset 128. Tambien busca en otros lados."""
    pos = data.find(b"DICM")
    return pos if pos >= 0 else None


def main():
    if not RUTA.exists():
        print(f"ERROR: no encuentro {RUTA}")
        sys.exit(1)

    tamano = RUTA.stat().st_size
    print(f"==========================================================")
    print(f"  ANALISIS DE: {RUTA.name}")
    print(f"  Tamano: {tamano:,} bytes ({tamano / (1024 * 1024):.2f} MB)")
    print(f"==========================================================\n")

    with open(RUTA, "rb") as f:
        data = f.read()

    # ---- 1) Cabecera ----
    print("[1] PRIMEROS 256 BYTES (hex + ascii)")
    print("-" * 60)
    print(hexdump_seccion(data, 0, 256))
    print()

    # ---- 2) DICOM? ----
    print("[2] BUSQUEDA DE FIRMA DICOM ('DICM')")
    print("-" * 60)
    pos_dicm = buscar_firma_dicom(data)
    if pos_dicm is None:
        print("No se encontro 'DICM'. No es DICOM estandar.\n")
    else:
        print(f"'DICM' encontrado en offset {pos_dicm} (0x{pos_dicm:x})")
        if pos_dicm == 128:
            print("Es DICOM con preambulo estandar.\n")
        else:
            print("Posicion no estandar, podria ser DICOM embebido.\n")

    # ---- 3) Otras firmas conocidas ----
    print("[3] BUSQUEDA DE FIRMAS DE IMAGEN COMUNES")
    print("-" * 60)
    firmas = {
        b"\xff\xd8\xff": "JPEG",
        b"\x89PNG": "PNG",
        b"II*\x00": "TIFF (little endian)",
        b"MM\x00*": "TIFF (big endian)",
        b"BM": "BMP",
        b"GIF8": "GIF",
        b"\x00\x00\x00\x0cjP": "JPEG 2000",
    }
    for firma, nombre in firmas.items():
        pos = data.find(firma)
        if pos >= 0:
            print(f"  {nombre}: offset {pos} (0x{pos:x})")
    print()

    # ---- 4) Strings ASCII ----
    print("[4] STRINGS ASCII (largo >= 6) - primeros 40")
    print("-" * 60)
    strings_ascii = buscar_strings_ascii(data, 6)
    print(f"Total encontradas: {len(strings_ascii)}")
    for off, txt in strings_ascii[:40]:
        print(f"  0x{off:08x}  {txt!r}")
    print()

    # ---- 5) Strings UTF-16 LE ----
    print("[5] STRINGS UTF-16 LE (largo >= 4) - primeros 60")
    print("-" * 60)
    strings_utf16 = buscar_strings_utf16le(data, 4)
    print(f"Total encontradas: {len(strings_utf16)}")
    for off, txt in strings_utf16[:60]:
        print(f"  0x{off:08x}  {txt!r}")
    print()

    # ---- 6) Distribucion del archivo ----
    print("[6] DISTRIBUCION DE CONTENIDO POR BLOQUE (1 MB)")
    print("-" * 60)
    bloque = 1024 * 1024
    for i in range(0, len(data), bloque):
        trozo = data[i:i + bloque]
        ceros = trozo.count(0)
        imprimibles = sum(1 for b in trozo if 32 <= b < 127)
        print(f"  Offset {i // bloque:>3} MB: "
              f"ceros={ceros / len(trozo) * 100:5.1f}%  "
              f"ascii={imprimibles / len(trozo) * 100:5.1f}%  "
              f"binario={(len(trozo) - ceros - imprimibles) / len(trozo) * 100:5.1f}%")
    print()

    print("==========================================================")
    print("  FIN DEL ANALISIS")
    print("==========================================================")


if __name__ == "__main__":
    main()

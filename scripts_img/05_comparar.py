"""
Compara dos archivos .img de Vieworks lado a lado:
  - Cabecera (primeros 256 bytes)
  - Tamano del bloque de pixeles
  - Bloque XML: longitud, primeros bytes raw, declaracion, diff por tag
"""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

FIRMA = "<?xml".encode("utf-16-le")


def localizar_xml(data: bytes) -> int:
    return data.find(FIRMA)


def cabecera(data: bytes, n: int = 64) -> str:
    out = []
    for i in range(0, n, 16):
        chunk = data[i:i + 16]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        out.append(f"{i:04x}  {hex_part:<48s}  {ascii_part}")
    return "\n".join(out)


def diff_attrs(a: dict, b: dict, prefix: str) -> list[str]:
    out = []
    keys = sorted(set(a) | set(b))
    for k in keys:
        va, vb = a.get(k), b.get(k)
        if va != vb:
            out.append(f"  {prefix}@{k}:")
            out.append(f"    plantilla = {va!r}")
            out.append(f"    generado  = {vb!r}")
    return out


def comparar_xml(xa: str, xb: str) -> None:
    ra = ET.fromstring(xa)
    rb = ET.fromstring(xb)

    # Paths que importan
    paths = [
        "PATIENT_INFO/Patient",
        "STUDY_INFO/Study",
        "STUDY_INFO/Patient",
        "STUDY_INFO/Scheduled",
        "STUDY_INFO/Institution",
        "SERIES_INFO/Series",
        "SERIES_INFO/PerformedProcedureStep",
        "SERIES_INFO/PerformingPhysician/Physician",
        "INSTANCE_INFO/Instance",
        "INSTANCE_INFO/Detector",
        "INSTANCE_INFO/Dose",
    ]

    print("\n[DIFF DE CAMPOS XML]\n" + "-" * 60)
    hay_diff = False
    for path in paths:
        na = ra.find(path)
        nb = rb.find(path)
        if na is None and nb is None:
            continue
        if na is None or nb is None:
            hay_diff = True
            print(f"  {path}: existe solo en {'generado' if na is None else 'plantilla'}")
            continue
        diffs = diff_attrs(dict(na.attrib), dict(nb.attrib), path)
        if diffs:
            hay_diff = True
            print("\n".join(diffs))
    if not hay_diff:
        print("  (sin diferencias en los paths comparados)")


def main():
    if len(sys.argv) != 3:
        print("Uso: python 05_comparar.py <plantilla.img> <generado.img>")
        sys.exit(1)
    a = Path(sys.argv[1]).read_bytes()
    b = Path(sys.argv[2]).read_bytes()
    pa, pb = localizar_xml(a), localizar_xml(b)
    print(f"PLANTILLA: {sys.argv[1]}")
    print(f"  tamano total: {len(a):,}")
    print(f"  xml inicio:   {pa} (0x{pa:x})")
    print(f"  xml tamano:   {len(a) - pa:,} bytes")
    print()
    print(f"GENERADO: {sys.argv[2]}")
    print(f"  tamano total: {len(b):,}")
    print(f"  xml inicio:   {pb} (0x{pb:x})")
    print(f"  xml tamano:   {len(b) - pb:,} bytes")
    print()

    # Cabeceras
    print("[CABECERA PLANTILLA] primeros 64 bytes")
    print(cabecera(a, 64))
    print()
    print("[CABECERA GENERADO] primeros 64 bytes")
    print(cabecera(b, 64))
    print()

    # Comparar bloque de pixeles byte a byte (solo igualdad)
    if pa == pb:
        iguales = a[:pa] == b[:pb]
        print(f"[PIXELES] mismo offset y bytes identicos: {iguales}")
    else:
        print(f"[PIXELES] offsets distintos: plantilla={pa} generado={pb}")

    # Primeros bytes del XML en RAW para ver el BOM/declaracion
    print()
    print("[XML RAW primeros 60 bytes plantilla]")
    print(cabecera(a[pa:pa + 60], 60))
    print()
    print("[XML RAW primeros 60 bytes generado]")
    print(cabecera(b[pb:pb + 60], 60))
    print()

    xa = a[pa:].decode("utf-16-le", errors="replace")
    xb = b[pb:].decode("utf-16-le", errors="replace")

    print("[DECLARACION XML]")
    print(f"  plantilla: {xa.splitlines()[0]!r}")
    print(f"  generado:  {xb.splitlines()[0]!r}")

    print()
    print("[ULTIMOS 60 chars XML]")
    print(f"  plantilla: ...{xa[-120:]!r}")
    print(f"  generado:  ...{xb[-120:]!r}")

    comparar_xml(xa, xb)


if __name__ == "__main__":
    main()

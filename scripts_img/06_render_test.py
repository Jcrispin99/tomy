"""
Prueba de extraccion de pixeles del .img Vieworks.
Intenta varias interpretaciones del bloque de pixeles y genera PNGs.
"""
import sys
from pathlib import Path

from PIL import Image


def windowing(img_f: Image.Image, w1: float, w2: float, modo: str) -> Image.Image:
    if modo == "centro_ancho":
        low = w1 - w2 / 2.0
        high = w1 + w2 / 2.0
    else:  # min_max
        low = w1
        high = w2
    rango = max(high - low, 1)
    return img_f.point(lambda x: max(0, min(255, (x - low) * 255 / rango)))


def main():
    ruta = Path(sys.argv[1] if len(sys.argv) > 1
                else "S2695I3233.img")
    salida = Path(__file__).resolve().parent
    data = ruta.read_bytes()
    W = H = 3072
    inicio_pixeles = 256

    print(f"Archivo: {ruta} ({len(data):,} bytes)")
    print(f"Bloque pixeles disponible: {len(data) - inicio_pixeles - 156000:,} bytes "
          f"(restando ~156KB de XML al final)")
    print(f"Si fueran uint16: {W*H*2:,} bytes ({W*H*2 / (1024*1024):.2f} MB)")
    print(f"Si fueran uint32: {W*H*4:,} bytes ({W*H*4 / (1024*1024):.2f} MB)")
    print()

    # Intento 1: uint16 LE, primer bloque
    print("=== Intento 1: uint16 LE primeros 18 MB ===")
    bloque1 = data[inicio_pixeles:inicio_pixeles + W*H*2]
    img1 = Image.frombytes('I;16', (W, H), bloque1)
    f = img1.convert('F')
    # Probar W1=5087 W2=9411 con interpretacion centro/ancho
    for modo in ["centro_ancho", "min_max"]:
        result = windowing(f, 5087, 9411, modo).convert('L')
        result.thumbnail((800, 800))
        out = salida / f"render_uint16LE_first_{modo}.png"
        result.save(out)
        print(f"  guardado: {out.name}")

    # Intento 2: uint16 LE, segundo bloque (offset +18 MB)
    print("\n=== Intento 2: uint16 LE segundo bloque ===")
    off2 = inicio_pixeles + W*H*2
    bloque2 = data[off2:off2 + W*H*2]
    if len(bloque2) >= W*H*2:
        img2 = Image.frombytes('I;16', (W, H), bloque2)
        f2 = img2.convert('F')
        for modo in ["centro_ancho", "min_max"]:
            result = windowing(f2, 5087, 9411, modo).convert('L')
            result.thumbnail((800, 800))
            out = salida / f"render_uint16LE_second_{modo}.png"
            result.save(out)
            print(f"  guardado: {out.name}")

    # Intento 3: detectar rango real de los primeros pixeles para auto-windowing
    print("\n=== Intento 3: auto-windowing (min/max real) ===")
    extremos = img1.getextrema()  # devuelve (min, max)
    print(f"  rango real bloque1: {extremos}")
    lo, hi = extremos
    result = f.point(lambda x: max(0, min(255, (x - lo) * 255 / max(hi - lo, 1)))).convert('L')
    result.thumbnail((800, 800))
    out = salida / "render_uint16LE_first_auto.png"
    result.save(out)
    print(f"  guardado: {out.name}")


if __name__ == "__main__":
    main()

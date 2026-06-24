"""
Prueba de extraccion de pixeles del .img Vieworks con varias interpretaciones.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def windowing(arr: np.ndarray, w1: float, w2: float, modo: str) -> np.ndarray:
    if modo == "centro_ancho":
        low = w1 - w2 / 2.0
        high = w1 + w2 / 2.0
    else:
        low = w1
        high = w2
    rango = max(high - low, 1)
    out = np.clip((arr.astype(np.float32) - low) * 255.0 / rango, 0, 255)
    return out.astype(np.uint8)


def auto_window(arr: np.ndarray, p_low=1, p_high=99) -> np.ndarray:
    """Auto-window basado en percentiles (descarta outliers)."""
    lo = np.percentile(arr, p_low)
    hi = np.percentile(arr, p_high)
    rango = max(hi - lo, 1)
    out = np.clip((arr.astype(np.float32) - lo) * 255.0 / rango, 0, 255)
    return out.astype(np.uint8)


def main():
    ruta = Path(sys.argv[1] if len(sys.argv) > 1 else "S2695I3233.img")
    salida = Path(__file__).resolve().parent
    data = ruta.read_bytes()
    W = H = 3072
    offset = 256
    n_px = W * H

    print(f"Archivo: {ruta} ({len(data):,} bytes)")
    print(f"Bloque disponible para pixeles: ~{(len(data) - offset - 156000) / (1024*1024):.1f} MB")
    print()

    # === Intento 1: uint16 LE primeros 18 MB ===
    print("=== uint16 LE primeros 18 MB ===")
    raw1 = np.frombuffer(data, dtype='<u2', count=n_px, offset=offset)
    arr1 = raw1.reshape((H, W))
    print(f"  min={arr1.min()} max={arr1.max()} mean={arr1.mean():.1f}")

    for modo in ("centro_ancho", "min_max"):
        out8 = windowing(arr1, 5087, 9411, modo)
        Image.fromarray(out8).resize((800, 800)).save(salida / f"render_uint16_first_{modo}.png")
        print(f"  guardado: render_uint16_first_{modo}.png")
    out_auto = auto_window(arr1)
    Image.fromarray(out_auto).resize((800, 800)).save(salida / "render_uint16_first_auto.png")
    print(f"  guardado: render_uint16_first_auto.png")

    # === Intento 2: uint16 LE segundo bloque ===
    print("\n=== uint16 LE segundo bloque (offset +18 MB) ===")
    off2 = offset + W * H * 2
    if off2 + n_px * 2 <= len(data):
        raw2 = np.frombuffer(data, dtype='<u2', count=n_px, offset=off2)
        arr2 = raw2.reshape((H, W))
        print(f"  min={arr2.min()} max={arr2.max()} mean={arr2.mean():.1f}")
        out_auto2 = auto_window(arr2)
        Image.fromarray(out_auto2).resize((800, 800)).save(salida / "render_uint16_second_auto.png")
        print(f"  guardado: render_uint16_second_auto.png")
    else:
        print("  no alcanza el bloque")

    # === Intento 3: uint32 LE completo ===
    print("\n=== uint32 LE completo (~36 MB) ===")
    if offset + n_px * 4 <= len(data) - 100000:
        raw32 = np.frombuffer(data, dtype='<u4', count=n_px, offset=offset)
        arr32 = raw32.reshape((H, W))
        print(f"  min={arr32.min()} max={arr32.max()} mean={arr32.mean():.1f}")
        out_auto32 = auto_window(arr32)
        Image.fromarray(out_auto32).resize((800, 800)).save(salida / "render_uint32_auto.png")
        print(f"  guardado: render_uint32_auto.png")


if __name__ == "__main__":
    main()

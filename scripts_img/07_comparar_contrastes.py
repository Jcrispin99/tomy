"""
Genera variantes de contraste sobre el mismo .img para elegir la mejor.
"""
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from scripts_img.render_img import _leer_dimensiones_y_window, PIXEL_OFFSET


def render_variante(ruta: Path, modo: str) -> bytes:
    data = ruta.read_bytes()
    w, h, wl = _leer_dimensiones_y_window(data)
    raw = np.frombuffer(data, dtype="<u2", count=w*h, offset=PIXEL_OFFSET)
    arr = raw.reshape((h, w))

    if modo == "xml_minmax":
        lo, hi = wl
    elif modo == "xml_centro_ancho":
        lo = wl[0] - wl[1] / 2.0
        hi = wl[0] + wl[1] / 2.0
    elif modo == "auto_p1_99":
        lo = float(np.percentile(arr, 1))
        hi = float(np.percentile(arr, 99.5))
    elif modo == "auto_p2_98":
        lo = float(np.percentile(arr, 2))
        hi = float(np.percentile(arr, 98))
    elif modo == "auto_p5_95":
        lo = float(np.percentile(arr, 5))
        hi = float(np.percentile(arr, 95))
    elif modo == "auto_p10_90":
        lo = float(np.percentile(arr, 10))
        hi = float(np.percentile(arr, 90))
    else:
        raise ValueError(modo)

    print(f"  {modo:25s}  rango ventana = [{lo:.0f}, {hi:.0f}]  width={hi-lo:.0f}")
    rango = max(hi - lo, 1.0)
    out8 = np.clip((arr.astype(np.float32) - lo) * 255.0 / rango, 0, 255).astype(np.uint8)
    img = Image.fromarray(out8, mode="L")
    img = ImageOps.invert(img)

    if modo.endswith("_autoctr"):
        img = ImageOps.autocontrast(img, cutoff=1)

    img.thumbnail((900, 900), Image.Resampling.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def main():
    ruta = Path("media/studies/2026/06/0000001_42175040.img")
    salida = Path("scripts_img")

    # Reportar stats de pixeles
    data = ruta.read_bytes()
    w, h, wl = _leer_dimensiones_y_window(data)
    raw = np.frombuffer(data, dtype="<u2", count=w*h, offset=PIXEL_OFFSET)
    print(f"Archivo: {ruta.name}")
    print(f"Pixeles: min={raw.min()} max={raw.max()} mean={raw.mean():.0f} std={raw.std():.0f}")
    print(f"WindowLevel del XML: W1={wl[0]:.0f}  W2={wl[1]:.0f}")
    print(f"Percentiles: p1={np.percentile(raw,1):.0f} p50={np.percentile(raw,50):.0f} p99={np.percentile(raw,99):.0f}")
    print()
    print("=== Generando variantes ===")

    for modo in ["xml_minmax", "xml_centro_ancho", "auto_p1_99",
                 "auto_p2_98", "auto_p5_95", "auto_p10_90"]:
        png = render_variante(ruta, modo)
        out = salida / f"variante_{modo}.png"
        out.write_bytes(png)


if __name__ == "__main__":
    main()

"""
Render de archivos .img de Vieworks a PNG visible.

Pixel layout (confirmado por experimentacion):
  - bytes 256..256+W*H*2 = pixeles uint16 little-endian (procesados)
  - W = H = 3072 por defecto (FXRD-1717VA)
  - bytes restantes hasta el XML = capa adicional (raw?), no necesaria para visualizar
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps


PIXEL_OFFSET = 256
DEFAULT_W = DEFAULT_H = 3072
FIRMA_XML = "<?xml".encode("utf-16-le")


def _leer_dimensiones_y_window(data: bytes) -> tuple[int, int, tuple[float, float] | None]:
    """Lee Width/Height/WindowLevel del XML embebido. Devuelve defaults si falla."""
    pos = data.find(FIRMA_XML)
    if pos < 0:
        return DEFAULT_W, DEFAULT_H, None
    try:
        texto = data[pos:].decode("utf-16-le", errors="replace")
        root = ET.fromstring(texto)
        inst = root.find("INSTANCE_INFO/Instance")
        w = int(inst.get("Width", DEFAULT_W)) if inst is not None else DEFAULT_W
        h = int(inst.get("Height", DEFAULT_H)) if inst is not None else DEFAULT_H
        wl = root.find(".//ThumbnailImage//WindowLevel")
        if wl is not None:
            return w, h, (float(wl.get("W1", 0)), float(wl.get("W2", 0)))
        return w, h, None
    except (ET.ParseError, ValueError, AttributeError):
        return DEFAULT_W, DEFAULT_H, None


def _aplicar_window(arr: np.ndarray, w1: float, w2: float, modo: str = "centro_ancho") -> np.ndarray:
    if modo == "centro_ancho":
        low = w1 - w2 / 2.0
        high = w1 + w2 / 2.0
    else:
        low, high = w1, w2
    rango = max(high - low, 1.0)
    out = np.clip((arr.astype(np.float32) - low) * 255.0 / rango, 0, 255)
    return out.astype(np.uint8)


def _auto_window(arr: np.ndarray, p_low: float = 1.0, p_high: float = 99.5) -> np.ndarray:
    lo = float(np.percentile(arr, p_low))
    hi = float(np.percentile(arr, p_high))
    rango = max(hi - lo, 1.0)
    out = np.clip((arr.astype(np.float32) - lo) * 255.0 / rango, 0, 255)
    return out.astype(np.uint8)


def renderizar_img(
    ruta: Path,
    max_size: int = 1024,
    invertir: bool = True,
    usar_window_xml: bool = False,
) -> bytes:
    """Devuelve los bytes PNG de la imagen renderizada.

    invertir=True deja convencion radiologica: huesos brillantes, aire oscuro.
    Por defecto usa ventana enfocada al cuerpo (percentiles 2-70%), que da
    buen contraste radiologico en imagenes Vieworks. El W1/W2 del XML resulta
    descalibrado cuando la mediana de los pixeles del cuerpo cae por debajo
    de W1, asi que solo se usa cuando se pide explicitamente.
    """
    data = Path(ruta).read_bytes()
    w, h, wl = _leer_dimensiones_y_window(data)
    n_px = w * h

    raw = np.frombuffer(data, dtype="<u2", count=n_px, offset=PIXEL_OFFSET)
    arr = raw.reshape((h, w))

    if usar_window_xml and wl is not None:
        out8 = _aplicar_window(arr, wl[0], wl[1], modo="min_max")
    else:
        out8 = _auto_window(arr, p_low=2.0, p_high=70.0)

    img = Image.fromarray(out8, mode="L")
    if invertir:
        img = ImageOps.invert(img)
    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()

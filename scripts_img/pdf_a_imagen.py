"""
Extrae la imagen embebida mas grande de un PDF y la guarda como JPG o PNG.

- Si el destino es .jpg: guarda los bytes JPEG originales tal cual (cero
  re-encoding, calidad maxima posible).
- Si el destino es .png: decodifica el JPEG y lo reencoda como PNG sin
  perdida (mismo bit-depth, color o gris segun venga).
- Si el PDF no trae imagenes embebidas, rasteriza la pagina a 4x para tener
  resolucion alta.
- Con --gris convierte a escala de grises (modo 'L', 1 canal) usando la
  luminancia ITU-R BT.601: Y = 0.299*R + 0.587*G + 0.114*B.

Uso:
    python -m scripts_img.pdf_a_imagen <entrada.pdf> <salida.jpg|.png> [--gris]
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import fitz  # pymupdf
from PIL import Image


def extraer_imagen(pdf_path: Path) -> tuple[bytes, str, int, int]:
    """Devuelve (bytes, extension, width, height) de la imagen embebida
    mas grande de la primera pagina. Si no hay imagenes, rasteriza.
    """
    with fitz.open(pdf_path) as doc:
        page = doc[0]
        imagenes = page.get_images(full=True)
        if imagenes:
            mejor = max(
                imagenes,
                key=lambda im: (
                    doc.extract_image(im[0])['width']
                    * doc.extract_image(im[0])['height']
                ),
            )
            info = doc.extract_image(mejor[0])
            return info['image'], info['ext'], info['width'], info['height']

        # Fallback: rasterizar a 4x para tener buena resolucion
        zoom = 4.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        buf = io.BytesIO()
        Image.frombytes('RGB', (pix.width, pix.height), pix.samples).save(
            buf, format='PNG', optimize=True,
        )
        return buf.getvalue(), 'png', pix.width, pix.height


def pdf_a_imagen(pdf_path: Path, salida: Path, gris: bool = False) -> Path:
    bytes_img, ext_origen, w, h = extraer_imagen(pdf_path)
    salida_ext = salida.suffix.lower().lstrip('.')
    salida.parent.mkdir(parents=True, exist_ok=True)

    si_copia_directa = (
        not gris
        and salida_ext in ('jpg', 'jpeg')
        and ext_origen in ('jpg', 'jpeg')
    )
    if si_copia_directa:
        salida.write_bytes(bytes_img)
        return salida

    img = Image.open(io.BytesIO(bytes_img))
    if gris and img.mode != 'L':
        img = img.convert('L')

    save_kwargs = {'optimize': True}
    if salida_ext in ('jpg', 'jpeg'):
        save_kwargs['quality'] = 95  # alta calidad para no degradar el origen
    img.save(salida, **save_kwargs)
    return salida


def _main_cli() -> None:
    args = sys.argv[1:]
    gris = False
    if '--gris' in args:
        gris = True
        args.remove('--gris')
    if len(args) < 2:
        print('Uso: python -m scripts_img.pdf_a_imagen '
              '<entrada.pdf> <salida.jpg|.png> [--gris]')
        sys.exit(1)
    pdf = Path(args[0])
    salida = Path(args[1])
    if not pdf.exists():
        print(f'No existe: {pdf}')
        sys.exit(1)

    ruta = pdf_a_imagen(pdf, salida, gris=gris)
    tam = ruta.stat().st_size
    modo = 'gris (L)' if gris else 'original (sin conversion de color)'
    print(f'Generado: {ruta} ({tam:,} bytes / {tam/1024:.1f} KB) [{modo}]')


if __name__ == '__main__':
    _main_cli()

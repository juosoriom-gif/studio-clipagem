"""Recomprime um PDF de paginas escaneadas: reduz resolucao e qualidade JPEG.
Usado quando um PDF vem gigante demais (paginas em alta resolucao sem
compressao). Sobrescreve o arquivo original.

Uso:
    py comprimir_pdf.py caminho\do\arquivo.pdf [--largura-max 1600] [--qualidade 82]
"""
import argparse
import io
import sys
from pathlib import Path

from pypdf import PdfReader
from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument("pdf")
ap.add_argument("--largura-max", type=int, default=1600)
ap.add_argument("--qualidade", type=int, default=82)
args = ap.parse_args()

origem = Path(args.pdf)
antes = origem.stat().st_size
reader = PdfReader(str(origem))

imagens = []
for i, page in enumerate(reader.pages, start=1):
    imgs = page.images
    if not imgs:
        print(f"pagina {i}: sem imagem embutida, pulando")
        continue
    img = imgs[0].image.convert("RGB")
    if img.width > args.largura_max:
        nova_altura = int(img.height * args.largura_max / img.width)
        img = img.resize((args.largura_max, nova_altura), Image.LANCZOS)
    imagens.append(img)
    print(f"pagina {i}: {img.width}x{img.height}")

if not imagens:
    sys.exit("Nenhuma imagem extraida - nada a fazer.")

buf = io.BytesIO()
imagens[0].save(buf, "PDF", save_all=True, append_images=imagens[1:],
                 resolution=150.0, quality=args.qualidade)
origem.write_bytes(buf.getvalue())
depois = origem.stat().st_size
print(f"{origem.name}: {antes:,} -> {depois:,} bytes ({100*depois/antes:.0f}%)")

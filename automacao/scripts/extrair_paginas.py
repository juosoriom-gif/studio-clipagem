"""Extrai as imagens embutidas de cada pagina de um PDF (uma imagem por pagina)."""
import sys
from pathlib import Path
from pypdf import PdfReader

pdf_path = Path(sys.argv[1])
destino = Path(sys.argv[2])
destino.mkdir(parents=True, exist_ok=True)

reader = PdfReader(str(pdf_path))
print(f"Paginas: {len(reader.pages)}")

for i, page in enumerate(reader.pages, start=1):
    imgs = page.images
    if not imgs:
        print(f"  pagina {i}: SEM imagem embutida")
        continue
    img = imgs[0]
    out = destino / f"{i:02d}.jpg"
    img.image.convert("RGB").save(out, "JPEG", quality=90)
    print(f"  pagina {i}: {out.name} ({out.stat().st_size:,} bytes)")

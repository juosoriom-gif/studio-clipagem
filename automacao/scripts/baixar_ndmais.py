"""Monta o PDF do ND Mais a partir da lista de paginas extraida do visualizador eflip.

O eflip serve cada pagina numa pasta propria (up, up1, up2, ...) com nome de
arquivo em timestamp - imprevisivel, por isso a lista vem de fora, raspada do DOM.
Algumas pastas trazem DUAS variantes; o script baixa as duas e fica com a maior
imagem, que e a de resolucao cheia.

Uso:
    py baixar_ndmais.py <edicao> "<mapa>" [--data AAAA-MM-DD]

    <mapa> no formato: up:123;up1:456,789;up2:...
"""

import argparse
import io
import json
import sys
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
CONFIG = RAIZ / "config.json"

CABECALHOS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
}
MODELO = "https://eflip.com.br/files/flip/RIC/{edicao}/{pasta}/{carimbo}.webp"


def ordem_pasta(nome):
    """up -> 0, up1 -> 1, up2 -> 2 ..."""
    return 0 if nome == "up" else int(nome[2:])


def interpretar_mapa(bruto):
    paginas = []
    for parte in bruto.strip().split(";"):
        if not parte:
            continue
        pasta, carimbos = parte.split(":")
        paginas.append((pasta.strip(), [c.strip() for c in carimbos.split(",") if c.strip()]))
    paginas.sort(key=lambda p: ordem_pasta(p[0]))
    return paginas


def melhor_variante(edicao, pasta, carimbos, sessao):
    """Baixa cada variante e devolve a de maior area em pixels."""
    melhor, melhor_area, melhor_carimbo = None, -1, None
    for carimbo in carimbos:
        url = MODELO.format(edicao=edicao, pasta=pasta, carimbo=carimbo)
        r = sessao.get(url, timeout=90)
        if r.status_code != 200 or len(r.content) < 5_000:
            print(f"  {pasta}/{carimbo}: ignorado ({r.status_code}, {len(r.content)} bytes)")
            continue
        img = Image.open(io.BytesIO(r.content))
        area = img.width * img.height
        if area > melhor_area:
            if melhor is not None:
                melhor.close()
            melhor, melhor_area, melhor_carimbo = img, area, carimbo
        else:
            img.close()
    return melhor, melhor_carimbo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edicao")
    ap.add_argument("mapa", help='formato: up:123;up1:456,789;...')
    ap.add_argument("--data", help="data da edicao AAAA-MM-DD (padrao: hoje)")
    args = ap.parse_args()

    with CONFIG.open(encoding="utf-8") as fh:
        cfg = json.load(fh)
    j = cfg["jornais"]["ndmais"]

    quando = datetime.strptime(args.data, "%Y-%m-%d") if args.data else datetime.now()
    paginas = interpretar_mapa(args.mapa)
    print(f"Edicao {args.edicao}: {len(paginas)} paginas")

    sessao = requests.Session()
    sessao.headers.update(CABECALHOS)

    imagens = []
    for i, (pasta, carimbos) in enumerate(paginas, start=1):
        img, carimbo = melhor_variante(args.edicao, pasta, carimbos, sessao)
        if img is None:
            print(f"  pagina {i} ({pasta}): FALHOU")
            continue
        escolha = f" [{len(carimbos)} variantes, escolhida {carimbo}]" if len(carimbos) > 1 else ""
        print(f"  pagina {i} ({pasta}): {img.width}x{img.height}{escolha}")
        # PDF nao aceita alpha; RGB e o formato seguro.
        imagens.append(img.convert("RGB") if img.mode != "RGB" else img)

    if not imagens:
        raise SystemExit("Nenhuma pagina baixada.")

    pasta_saida = Path(cfg["pasta_saida"]) / f"{quando:%Y-%m-%d}"
    pasta_saida.mkdir(parents=True, exist_ok=True)
    destino = pasta_saida / f"{quando:%Y%m%d}_{j['id_veiculo']}_{j['slug']}.pdf"

    imagens[0].save(destino, "PDF", save_all=True, append_images=imagens[1:], resolution=150.0)
    for img in imagens:
        img.close()

    print(f"\nPDF gerado: {destino}  ({destino.stat().st_size:,} bytes)")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)

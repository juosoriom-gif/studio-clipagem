"""Baixa a edicao mais recente de um jornal pagina por pagina e une tudo num unico PDF.

Uso:
    py baixar_jornal.py agazeta                 # detecta a edicao mais recente
    py baixar_jornal.py agazeta --edicao 8981   # forca uma edicao especifica
    py baixar_jornal.py agazeta --so-verificar  # so diz qual e a mais recente
"""

import argparse
import io
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests
from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
CONFIG = RAIZ / "config.json"
LOGS = RAIZ / "logs"

# Sem User-Agent o servidor devolve 403 em algumas edicoes.
CABECALHOS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
}

# Quantos 404 seguidos aceitar antes de concluir que acabou.
TOLERANCIA_EDICAO = 3
TOLERANCIA_PAGINA = 2


def log(msg):
    carimbo = datetime.now().strftime("%H:%M:%S")
    linha = f"[{carimbo}] {msg}"
    print(linha, flush=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    arquivo = LOGS / f"{datetime.now():%Y-%m-%d}.log"
    with arquivo.open("a", encoding="utf-8") as fh:
        fh.write(linha + "\n")


def carregar_config():
    with CONFIG.open(encoding="utf-8") as fh:
        return json.load(fh)


def existe(url, sessao):
    """True se a URL responde 200 com uma imagem de verdade."""
    try:
        r = sessao.head(url, timeout=25, allow_redirects=True)
        if r.status_code != 200:
            return False
        tipo = r.headers.get("Content-Type", "")
        tamanho = int(r.headers.get("Content-Length", 0) or 0)
        # Paginas reais passam de 10 KB; abaixo disso costuma ser placeholder.
        return tipo.startswith("image/") and tamanho > 10_000
    except requests.RequestException:
        return False


def descobrir_edicao_mais_recente(modelo, semente, sessao):
    """Sobe a partir da semente ate encontrar TOLERANCIA_EDICAO faltas seguidas."""
    if not existe(modelo.format(edicao=semente, pagina=1), sessao):
        raise SystemExit(
            f"A edicao semente {semente} nao respondeu. Ajuste 'edicao_semente' no config.json."
        )

    atual = semente
    candidata = semente + 1
    faltas = 0
    while faltas < TOLERANCIA_EDICAO:
        if existe(modelo.format(edicao=candidata, pagina=1), sessao):
            atual = candidata
            faltas = 0
            log(f"  edicao {candidata} existe")
        else:
            faltas += 1
        candidata += 1
    return atual


def baixar_paginas(modelo, edicao, sessao):
    """Baixa 1.jpg, 2.jpg, ... ate as paginas acabarem. Devolve lista de bytes."""
    paginas = []
    numero = 1
    faltas = 0
    while faltas < TOLERANCIA_PAGINA:
        url = modelo.format(edicao=edicao, pagina=numero)
        try:
            r = sessao.get(url, timeout=60)
        except requests.RequestException as erro:
            log(f"  pagina {numero}: falha de rede ({erro}) - tentando a proxima")
            faltas += 1
            numero += 1
            continue

        if r.status_code == 200 and len(r.content) > 10_000:
            paginas.append(r.content)
            log(f"  pagina {numero}: {len(r.content):,} bytes")
            faltas = 0
        else:
            faltas += 1
        numero += 1

    return paginas


def montar_pdf(paginas, destino):
    """Une os JPGs num unico PDF, na ordem."""
    imagens = []
    for bruto in paginas:
        img = Image.open(io.BytesIO(bruto))
        # PDF nao aceita alpha; RGB e o formato seguro.
        if img.mode != "RGB":
            img = img.convert("RGB")
        imagens.append(img)

    destino.parent.mkdir(parents=True, exist_ok=True)
    imagens[0].save(
        destino, "PDF", save_all=True, append_images=imagens[1:], resolution=150.0
    )
    for img in imagens:
        img.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jornal", help="chave do jornal no config.json (ex: agazeta)")
    ap.add_argument("--edicao", type=int, help="forca um numero de edicao")
    ap.add_argument("--so-verificar", action="store_true",
                    help="apenas informa a edicao mais recente, sem baixar")
    ap.add_argument("--guardar-jpg", action="store_true",
                    help="guarda tambem os JPGs soltos, alem do PDF")
    args = ap.parse_args()

    cfg = carregar_config()
    jornais = cfg["jornais"]
    if args.jornal not in jornais:
        raise SystemExit(f"Jornal '{args.jornal}' nao existe no config.json. "
                         f"Disponiveis: {', '.join(jornais)}")

    j = jornais[args.jornal]
    if j.get("tipo") != "paginas_jpg":
        raise SystemExit(f"'{args.jornal}' ainda nao tem o metodo de download definido "
                         f"(tipo = {j.get('tipo')}).")

    modelo = j["url_modelo"]
    sessao = requests.Session()
    sessao.headers.update(CABECALHOS)

    log(f"=== {j['nome']} ===")

    if args.edicao:
        edicao = args.edicao
        log(f"Edicao forcada pelo parametro: {edicao}")
    else:
        log(f"Procurando a edicao mais recente a partir da {j['edicao_semente']}...")
        edicao = descobrir_edicao_mais_recente(modelo, j["edicao_semente"], sessao)
        log(f"Edicao mais recente: {edicao}")
        if edicao == j["edicao_semente"]:
            log("Nenhuma edicao nova desde a ultima rodada - nao ha jornal novo hoje. Nada a baixar.")
            return

    if args.so_verificar:
        return

    log("Baixando paginas...")
    paginas = baixar_paginas(modelo, edicao, sessao)
    if not paginas:
        raise SystemExit("Nenhuma pagina baixada - nada a fazer.")
    log(f"Total: {len(paginas)} paginas")

    agora = datetime.now()
    # A Gazeta publica a edicao de amanha hoje a noite (~20h30-23h30). Rodando de
    # madrugada (ex: 5h) a edicao do dia already e a de hoje; rodando a noite (ex:
    # 23h30) a edicao ja disponivel e a de amanha - por isso o +1 dia nesse caso.
    data_edicao = agora + timedelta(days=1) if agora.hour >= 12 else agora
    base = f"{data_edicao:%Y%m%d}_{j['id_veiculo']}_{j['slug']}"
    # Uma pasta por dia (da EDICAO, nao da execucao), com todos os jornais daquele dia juntos.
    pasta = Path(cfg["pasta_saida"]) / f"{data_edicao:%Y-%m-%d}"
    pdf = pasta / f"{base}.pdf"

    montar_pdf(paginas, pdf)
    log(f"PDF gerado: {pdf}  ({pdf.stat().st_size:,} bytes)")

    if args.guardar_jpg:
        # Subpasta propria, senao as paginas de jornais diferentes se misturam.
        soltas = pasta / f"{base}_paginas"
        soltas.mkdir(parents=True, exist_ok=True)
        for i, bruto in enumerate(paginas, start=1):
            (soltas / f"{i}.jpg").write_bytes(bruto)
        log(f"JPGs soltos guardados em {soltas}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)

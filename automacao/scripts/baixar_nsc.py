"""Baixa DC, AN e Santa (grupo NSC) direto, SEM navegador e SEM login.

Descoberta de 01/08/2026: a edicao inteira fica num PDF publico com nome
previsivel. Nao precisa abrir o site, nem ler o indice, nem o ed_impressa_jn.

    flip.nsctotal.com.br/wp-content/uploads/{AAAA}/{MM}/{arquivo}_{AAAAMMDD}_todas.pdf

A unica pegadinha e a pasta: ela e o mes do UPLOAD no WordPress, nao o mes da
edicao. A edicao de 01/08/2026 estava em /2026/07/. Por isso o script tenta o
mes da edicao e os dois anteriores.

Uso:
    py baixar_nsc.py                  # edicao do dia (hoje)
    py baixar_nsc.py --data 2026-08-01
    py baixar_nsc.py --so-verificar
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
CONFIG = RAIZ / "config.json"
LOGS = RAIZ / "logs"

CABECALHOS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
}

BASE = "https://flip.nsctotal.com.br/wp-content/uploads/{ano}/{mes:02d}/{arquivo}_{data}_todas.pdf"

# chave no config -> nome do arquivo no servidor
VEICULOS = {
    "dc": "diariocatarinense",
    "an": "anoticia",
    "santa": "jornaldesantacatarina",
}


def log(msg):
    linha = f"[{datetime.now():%H:%M:%S}] {msg}"
    print(linha, flush=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    with (LOGS / f"{datetime.now():%Y-%m-%d}.log").open("a", encoding="utf-8") as fh:
        fh.write(linha + "\n")


def meses_candidatos(quando):
    """Mes da edicao e os dois anteriores - a pasta e a do upload, nao a da edicao."""
    saida = []
    ano, mes = quando.year, quando.month
    for _ in range(3):
        saida.append((ano, mes))
        mes -= 1
        if mes == 0:
            mes, ano = 12, ano - 1
    return saida


def achar_pdf(arquivo, quando, sessao):
    """Devolve (url, tamanho) do primeiro candidato que for um PDF de verdade."""
    data = f"{quando:%Y%m%d}"
    for ano, mes in meses_candidatos(quando):
        url = BASE.format(ano=ano, mes=mes, arquivo=arquivo, data=data)
        try:
            r = sessao.head(url, timeout=30, allow_redirects=True)
        except requests.RequestException:
            continue
        tamanho = int(r.headers.get("Content-Length", 0) or 0)
        tipo = r.headers.get("Content-Type", "")
        # O servidor responde 200 com 0 byte para arquivo inexistente - por isso
        # exigir application/pdf E tamanho de verdade.
        if r.status_code == 200 and "pdf" in tipo and tamanho > 100_000:
            return url, tamanho
    return None, 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", help="data da edicao AAAA-MM-DD (padrao: hoje)")
    ap.add_argument("--so-verificar", action="store_true")
    args = ap.parse_args()

    with CONFIG.open(encoding="utf-8") as fh:
        cfg = json.load(fh)

    quando = datetime.strptime(args.data, "%Y-%m-%d") if args.data else datetime.now()
    sessao = requests.Session()
    sessao.headers.update(CABECALHOS)

    pasta = Path(cfg["pasta_saida"]) / f"{quando:%Y-%m-%d}"
    log(f"=== NSC - edicao de {quando:%d/%m/%Y} ===")

    falhas = 0
    for chave, arquivo in VEICULOS.items():
        j = cfg["jornais"][chave]
        url, tamanho = achar_pdf(arquivo, quando, sessao)
        if not url:
            log(f"{j['nome']}: NAO ENCONTRADO para {quando:%d/%m/%Y}")
            falhas += 1
            continue

        log(f"{j['nome']}: {tamanho/1048576:.1f} MB")
        if args.so_verificar:
            continue

        pasta.mkdir(parents=True, exist_ok=True)
        destino = pasta / f"{quando:%Y%m%d}_{j['id_veiculo']}_{j['slug']}.pdf"
        r = sessao.get(url, timeout=600)
        destino.write_bytes(r.content)
        log(f"  -> {destino.name}")

    if falhas:
        log(f"{falhas} veiculo(s) sem edicao nesta data.")
    return 1 if falhas == len(VEICULOS) else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)

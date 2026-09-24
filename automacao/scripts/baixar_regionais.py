"""Baixa a edicao mais recente de jornais regionais diversos, cada um com seu
proprio padrao de acesso. Descoberto em 15/09/2026 a pedido do usuario.

Pasta e nome de arquivo usam a DATA DA EDICAO (nao a data em que o script
rodou) - mesma regra do resto do projeto. Quando a fonte nao expoe uma data
confiavel (tribuna), usa a data de hoje mesmo, documentado caso a caso abaixo.

Cada fonte so e baixada quando a edicao muda: estado_regionais.json (fora da
pasta de saida) guarda o identificador da ultima edicao processada por fonte
(numero, id, hash...), independente do PDF ainda estar ou nao em "jornais do
interior" - sem isso, fontes semanais/mensais eram rebaixadas TODO DIA que o
script rodava, porque o PDF costuma sair dessa pasta depois de entrar na
clipagem do dia (bug encontrado em 21/09/2026, casos condominiosc e tribuna:
o mesmo PDF acumulava uma copia nova por dia). tribuna nao tem numero de
edicao visivel, entao usa a propria URL do PDF (hash muda quando sai edicao
nova) como identificador.

Fontes cobertas (chave no config.json):
    jcjoinville      - pasta publica do Google Drive, PDF unico (semanal)
    folhadesbravador - PDF publico com nome previsivel a partir da data (semanal)
    olider           - PDF publico listado na home, wh3.com.br (semanal)
    hcnoticias       - paginas JPG numeradas, mesmo padrao da A Gazeta (semanal)
    condominiosc     - PDF publico listado na pagina (mensal)
    revistafrancisca - PDF publico com nome previsivel a partir do mes (mensal)
    tribuna          - PDF publico, mas o link tem hash aleatorio: precisa
                        raspar a pagina toda vez. Sem data visivel na pagina -
                        usa a data de hoje (dia em que a mudanca foi notada).
    voltagrande      - viewer pubhtml5.com; o 'bookConfig' do config.js e
                        ofuscado, mas a chave 'fliphtml5_pages' do mesmo
                        arquivo e JSON puro com o hash de cada pagina.

Fontes AINDA NAO resolvidas (nao estao no COLETORES, precisam do Chrome do
usuario via claude-in-chrome para ver o link do PDF - ver observacao de
"folhadechapeco" no config.json):
    folhadechapeco - mesma plataforma do Diario do Iguacu (diregional.com.br).
                     PDF final e publico, mas o indice/pagina da edicao pede
                     sessao logada para revelar o link. Coletor manual, nao
                     roda por aqui.

Uso:
    py baixar_regionais.py                  # baixa todos os resolvidos
    py baixar_regionais.py jcjoinville      # baixa so um
    py baixar_regionais.py --so-verificar   # so mostra o que seria baixado
"""

import argparse
import io
import json
import re
import sys
import urllib.parse
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
CONFIG = RAIZ / "config.json"
LOGS = RAIZ / "logs"
ESTADO = RAIZ / "estado_regionais.json"

CABECALHOS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
}

MESES_PT = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4, "maio": 5,
    "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10,
    "novembro": 11, "dezembro": 12,
}
MESES_PT_ABREV = {  # "10 de set." etc (Google Drive)
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}


def log(msg):
    linha = f"[{datetime.now():%H:%M:%S}] {msg}"
    print(linha, flush=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    with (LOGS / f"{datetime.now():%Y-%m-%d}.log").open("a", encoding="utf-8") as fh:
        fh.write(linha + "\n")


def destino_pdf(cfg, chave, data_edicao):
    j = cfg["jornais"][chave]
    # jornais regionais ficam separados dos jornais da clipagem das 5h,
    # tudo direto dentro de "jornais do interior" - sem subpasta de data
    # (pedido do usuario em 15/09/2026); a data ja vai no nome do arquivo.
    raiz = cfg.get("pasta_saida_interior", cfg["pasta_saida"])
    return Path(raiz) / f"{data_edicao:%Y%m%d}_{j['id_veiculo']}_{j['slug']}.pdf"


def salvar(destino, conteudo):
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(conteudo)


def ja_existe(destino):
    """Edicao ja baixada anteriormente - evita baixar de novo o que ja temos."""
    return destino.exists() and destino.stat().st_size > 0


def carregar_estado():
    if ESTADO.exists():
        try:
            return json.loads(ESTADO.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def salvar_estado(estado):
    ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")


def ja_processado(estado, chave, identificador):
    """A mesma edicao ja foi baixada numa execucao anterior - mesmo que o PDF
    tenha saido depois da pasta "jornais do interior" (ex.: movido pra montar
    a clipagem do dia), nao faz sentido rebaixar todo dia so porque o arquivo
    nao esta mais la. Guarda o identificador da edicao (numero, id, hash...)
    por fonte em estado_regionais.json, fora da pasta de saida."""
    return estado.get(chave) == str(identificador)


def marcar_processado(estado, chave, identificador):
    estado[chave] = str(identificador)
    salvar_estado(estado)


# --------------------------------------------------------------------------
# jcjoinville - pasta publica do Google Drive
# --------------------------------------------------------------------------
PASTA_DRIVE_JC = "12aREuuGkSb4dsBocg37VUzeMv6f5esAc"


def achar_jcjoinville(sessao):
    url = f"https://drive.google.com/embeddedfolderview?id={PASTA_DRIVE_JC}#grid"
    r = sessao.get(url, timeout=30)
    r.raise_for_status()
    blocos = re.findall(
        r'id="entry-([\w-]+)"[^<]*<div class="flip-entry-info"><a href="[^"]+"[^>]*>'
        r'.*?<div class="flip-entry-title">([^<]+)</div></a></div>'
        r'<div class="flip-entry-last-modified"><div>([^<]+)</div>',
        r.text, re.S,
    )
    if not blocos:
        return None
    file_id, titulo, modificado = blocos[-1]  # ordem cronologica crescente
    m = re.match(r"(\d+)\s+de\s+(\w+)\.?", modificado.strip())
    data = None
    if m:
        dia, mes_abrev = m.groups()
        mes = MESES_PT_ABREV.get(mes_abrev.lower().rstrip("."))
        if mes:
            ano = datetime.now().year
            data = datetime(ano, mes, int(dia))
            if data > datetime.now():
                data = datetime(ano - 1, mes, int(dia))
    return {"file_id": file_id, "titulo": titulo.strip(), "data": data or datetime.now()}


def baixar_jcjoinville(cfg, sessao, estado, so_verificar):
    j = cfg["jornais"]["jcjoinville"]
    info = achar_jcjoinville(sessao)
    if not info:
        log(f"{j['nome']}: nao encontrei nenhum arquivo na pasta do Drive")
        return False
    log(f"{j['nome']}: {info['titulo']} ({info['data']:%d/%m/%Y})")
    if so_verificar:
        return True

    if ja_processado(estado, "jcjoinville", info["file_id"]):
        log("  edicao ja processada anteriormente, pulando")
        return True

    destino = destino_pdf(cfg, "jcjoinville", info["data"])
    if ja_existe(destino):
        log(f"  ja baixado ({destino.name}), pulando")
        marcar_processado(estado, "jcjoinville", info["file_id"])
        return True

    url = f"https://drive.google.com/uc?export=download&id={info['file_id']}"
    r = sessao.get(url, timeout=120)
    r.raise_for_status()
    if not r.content.startswith(b"%PDF"):
        log("  ERRO: resposta nao parece um PDF (arquivo grande demais para o Drive liberar direto?)")
        return False

    salvar(destino, r.content)
    log(f"  -> {destino} ({len(r.content):,} bytes)")
    marcar_processado(estado, "jcjoinville", info["file_id"])
    return True


# --------------------------------------------------------------------------
# folhadesbravador - PDF com nome previsivel a partir da data da edicao
# --------------------------------------------------------------------------
def achar_folhadesbravador(sessao):
    url = "https://folhadesbravador.com.br/versao-impressa-da-folha-desbravador/"
    r = sessao.get(url, timeout=30)
    r.raise_for_status()
    m = re.search(
        r"Edi[cç][aã]o\s+(\d+)\s+da\s+Folha\s+Desbravador\s*[–-]\s*"
        r"(\d{2})\s+de\s+(\w+)\s+de\s+(\d{4})",
        r.text, re.I,
    )
    if not m:
        return None
    edicao, dia, mes_nome, ano = m.groups()
    mes = MESES_PT.get(mes_nome.lower())
    if not mes:
        return None
    return {"edicao": edicao, "data": datetime(int(ano), mes, int(dia))}


def baixar_folhadesbravador(cfg, sessao, estado, so_verificar):
    j = cfg["jornais"]["folhadesbravador"]
    info = achar_folhadesbravador(sessao)
    if not info:
        log(f"{j['nome']}: nao consegui achar a edicao mais recente no site")
        return False
    data = info["data"]
    log(f"{j['nome']}: edicao {info['edicao']} - {data:%d/%m/%Y}")
    if so_verificar:
        return True

    if ja_processado(estado, "folhadesbravador", info["edicao"]):
        log("  edicao ja processada anteriormente, pulando")
        return True

    destino = destino_pdf(cfg, "folhadesbravador", data)
    if ja_existe(destino):
        log(f"  ja baixado ({destino.name}), pulando")
        marcar_processado(estado, "folhadesbravador", info["edicao"])
        return True

    nome_arquivo = f"Folha-Desbravador-Cores-{data:%d-%m-%Y}.pdf"
    for ano, mes in ((data.year, data.month), (data.year, data.month - 1 or 12)):
        url = f"https://folhadesbravador.com.br/wp-content/uploads/{ano}/{mes:02d}/{nome_arquivo}"
        r = sessao.get(url, timeout=120)
        if r.status_code == 200 and r.content[:4] == b"%PDF":
            salvar(destino, r.content)
            log(f"  -> {destino} ({len(r.content):,} bytes)")
            marcar_processado(estado, "folhadesbravador", info["edicao"])
            return True
    log("  ERRO: PDF nao encontrado em nenhuma pasta de upload candidata")
    return False


# --------------------------------------------------------------------------
# olider (Jornal O Lider - wh3.com.br) - PDF listado na home
# --------------------------------------------------------------------------
def achar_olider(sessao):
    url = "https://wh3.com.br/olider/mh"
    r = sessao.get(url, timeout=30)
    r.raise_for_status()
    candidatos = re.findall(
        r'https://wh3\.com\.br/galerias/olider/[^"\')]+_ed_(\d+)\.pdf', r.text
    )
    if not candidatos:
        return None
    maior = max(candidatos, key=int)
    m = re.search(r'(https://wh3\.com\.br/galerias/olider/[^"\')]+_ed_' + maior + r'\.pdf)', r.text)
    url_pdf = m.group(1)

    # a pagina nao mostra a data ao lado da edicao, mas mostra "Destaques da
    # semana - DD/MM a DD/MM" logo depois - a edicao e datada pelo FIM dessa
    # semana (confirmado: semanas seguintes tem 7 dias de diferenca)
    data = datetime.now()
    m_semana = re.search(r"Destaques da semana\s*-\s*\d{2}/\d{2}\s*\S\s*(\d{2})/(\d{2})", r.text)
    if m_semana:
        dia, mes = int(m_semana.group(1)), int(m_semana.group(2))
        ano = datetime.now().year
        try:
            data = datetime(ano, mes, dia)
            if data > datetime.now():
                data = datetime(ano - 1, mes, dia)
        except ValueError:
            data = datetime.now()

    return {"url": url_pdf, "edicao": maior, "data": data}


def baixar_olider(cfg, sessao, estado, so_verificar):
    j = cfg["jornais"]["olider"]
    info = achar_olider(sessao)
    if not info:
        log(f"{j['nome']}: nao encontrei PDF na home")
        return False
    log(f"{j['nome']}: edicao {info['edicao']} ({info['data']:%d/%m/%Y})")
    if so_verificar:
        return True

    if ja_processado(estado, "olider", info["edicao"]):
        log("  edicao ja processada anteriormente, pulando")
        return True

    destino = destino_pdf(cfg, "olider", info["data"])
    if ja_existe(destino):
        log(f"  ja baixado ({destino.name}), pulando")
        marcar_processado(estado, "olider", info["edicao"])
        return True

    r = sessao.get(info["url"], timeout=120)
    r.raise_for_status()
    if r.content[:4] != b"%PDF":
        log("  ERRO: resposta nao parece PDF")
        return False

    salvar(destino, r.content)
    log(f"  -> {destino} ({len(r.content):,} bytes)")
    marcar_processado(estado, "olider", info["edicao"])
    return True


# --------------------------------------------------------------------------
# hcnoticias - paginas JPG numeradas, mesmo padrao da A Gazeta
# --------------------------------------------------------------------------
def achar_hcnoticias(sessao):
    url = "https://hcnoticias.com.br/edicoes-impressas"
    r = sessao.get(url, timeout=30)
    r.raise_for_status()
    m = re.search(
        r'title="Edi[cç][aã]o - (\d{2}/\d{2}/\d{4})"><img[^>]+src="'
        r'https://hcnoticias\.com\.br/img/edicoes/(\d+)/01\.jpg"',
        r.text,
    )
    if not m:
        return None
    data_str, edicao_id = m.groups()
    data = datetime.strptime(data_str, "%d/%m/%Y")

    r2 = sessao.get(f"{url}/visualizar/{edicao_id}", timeout=30)
    r2.raise_for_status()
    paginas = sorted(set(re.findall(rf"/img/edicoes/{edicao_id}/(\d+)\.jpg", r2.text)))
    return {"edicao_id": edicao_id, "data": data, "paginas": paginas}


def baixar_hcnoticias(cfg, sessao, estado, so_verificar):
    j = cfg["jornais"]["hcnoticias"]
    info = achar_hcnoticias(sessao)
    if not info or not info["paginas"]:
        log(f"{j['nome']}: nao encontrei edicao/paginas")
        return False
    log(f"{j['nome']}: edicao {info['edicao_id']} ({info['data']:%d/%m/%Y}), {len(info['paginas'])} paginas")
    if so_verificar:
        return True

    if ja_processado(estado, "hcnoticias", info["edicao_id"]):
        log("  edicao ja processada anteriormente, pulando")
        return True

    destino = destino_pdf(cfg, "hcnoticias", info["data"])
    if ja_existe(destino):
        log(f"  ja baixado ({destino.name}), pulando")
        marcar_processado(estado, "hcnoticias", info["edicao_id"])
        return True

    imagens = []
    for pagina in info["paginas"]:
        url = f"https://hcnoticias.com.br/img/edicoes/{info['edicao_id']}/{pagina}.jpg"
        r = sessao.get(url, timeout=60)
        if r.status_code != 200 or len(r.content) < 10_000:
            log(f"  pagina {pagina}: falhou, pulando")
            continue
        imagens.append(r.content)
    if not imagens:
        log("  ERRO: nenhuma pagina baixada")
        return False

    pil_imgs = []
    for bruto in imagens:
        img = Image.open(io.BytesIO(bruto))
        if img.mode != "RGB":
            img = img.convert("RGB")
        pil_imgs.append(img)

    destino.parent.mkdir(parents=True, exist_ok=True)
    pil_imgs[0].save(destino, "PDF", save_all=True, append_images=pil_imgs[1:], resolution=150.0)
    for img in pil_imgs:
        img.close()
    log(f"  -> {destino} ({len(imagens)} paginas, {destino.stat().st_size:,} bytes)")
    marcar_processado(estado, "hcnoticias", info["edicao_id"])
    return True


# --------------------------------------------------------------------------
# condominiosc - PDF listado na pagina (mensal)
# --------------------------------------------------------------------------
def achar_condominiosc(sessao):
    url = "https://condominiosc.com.br/versao-impressa"
    r = sessao.get(url, timeout=30)
    r.raise_for_status()
    candidatos = re.findall(
        r'(https://condominiosc\.com\.br/media/k2/attachments/'
        r'Jornal_dos_Condominios_-_ED(\d+)[^"\')]*\.pdf)', r.text
    )
    if not candidatos:
        return None
    candidatos.sort(key=lambda par: int(par[1]), reverse=True)
    url_pdf, edicao = candidatos[0]

    # a pagina rotula o mes de CAPA do numero seguinte com o numero deste
    # (bug do proprio site: o card do ED296 mostra titulo "EDICAO 295 AGOSTO
    # 26"). O padrao observado e: mes de capa X -> edicao sai em 01 do mes
    # seguinte (ED296=agosto -> saiu 01/09). Le o mes de qualquer jeito e
    # soma 1. O cabecalho "EDIÇÃO ..." fica ANTES do link, mas a distancia
    # ate ele varia (a pagina ja teve titulos duplicados na mesma faixa) -
    # por isso procura o cabecalho mais proximo antes do link, sem depender
    # de uma janela de tamanho fixo.
    m = re.search(re.escape(f"ED{edicao}") + r'.{0,10}pdf"', r.text)
    data = None
    m_mes = None
    if m:
        for cand in re.finditer(r"EDI[ÇC][ÃA]O\s+\d+\s+(\w+)\s+(\d{2})", r.text[:m.start()], re.I):
            m_mes = cand
    if m_mes:
        mes_nome, ano_curto = m_mes.groups()
        mes = MESES_PT.get(mes_nome.lower()) or {"mar": 3, "set": 9}.get(mes_nome.lower())
        if mes:
            mes += 1
            ano = 2000 + int(ano_curto)
            if mes == 13:
                mes, ano = 1, ano + 1
            data = datetime(ano, mes, 1)
    return {"url": url_pdf, "edicao": edicao, "data": data or datetime.now()}


def baixar_condominiosc(cfg, sessao, estado, so_verificar):
    j = cfg["jornais"]["condominiosc"]
    info = achar_condominiosc(sessao)
    if not info:
        log(f"{j['nome']}: nao encontrei PDF na pagina")
        return False
    log(f"{j['nome']}: edicao {info['edicao']} ({info['data']:%d/%m/%Y})")
    if so_verificar:
        return True

    if ja_processado(estado, "condominiosc", info["edicao"]):
        log("  edicao ja processada anteriormente, pulando")
        return True

    destino = destino_pdf(cfg, "condominiosc", info["data"])
    if ja_existe(destino):
        log(f"  ja baixado ({destino.name}), pulando")
        marcar_processado(estado, "condominiosc", info["edicao"])
        return True

    r = sessao.get(info["url"], timeout=120)
    r.raise_for_status()
    if r.content[:4] != b"%PDF":
        log("  ERRO: resposta nao parece PDF")
        return False

    salvar(destino, r.content)
    log(f"  -> {destino} ({len(r.content):,} bytes)")
    marcar_processado(estado, "condominiosc", info["edicao"])
    return True


# --------------------------------------------------------------------------
# revistafrancisca - PDF com nome previsivel a partir do mes da edicao
# --------------------------------------------------------------------------
def achar_revistafrancisca(sessao):
    url = "https://revistafrancisca.com.br/edicoes/"
    r = sessao.get(url, timeout=30)
    r.raise_for_status()
    texto = re.sub(r"<[^>]+>", " ", r.text)
    m = re.search(r"Edi[cç][aã]o\s+(\d+)\s*(.+?)LEIA A REVISTA", texto, re.S | re.I)
    if not m:
        return None
    edicao, corpo = m.group(1), m.group(2)
    mes_m = re.search(r"\b(" + "|".join(MESES_PT) + r")\b", corpo, re.I)
    if not mes_m:
        return None
    mes = MESES_PT[mes_m.group(1).lower()]
    ano = datetime.now().year
    if mes - datetime.now().month > 6:
        ano -= 1
    return {"edicao": edicao, "data": datetime(ano, mes, 1)}


def baixar_revistafrancisca(cfg, sessao, estado, so_verificar):
    j = cfg["jornais"]["revistafrancisca"]
    info = achar_revistafrancisca(sessao)
    if not info:
        log(f"{j['nome']}: nao consegui achar a edicao mais recente no site")
        return False
    data = info["data"]
    log(f"{j['nome']}: edicao {info['edicao']} - {data:%m/%Y}")
    if so_verificar:
        return True

    if ja_processado(estado, "revistafrancisca", info["edicao"]):
        log("  edicao ja processada anteriormente, pulando")
        return True

    destino = destino_pdf(cfg, "revistafrancisca", data)
    if ja_existe(destino):
        log(f"  ja baixado ({destino.name}), pulando")
        marcar_processado(estado, "revistafrancisca", info["edicao"])
        return True

    mes_abrev = {v: k[:3] for k, v in MESES_PT.items() if k != "marco"}[data.month]
    nome_arquivo = f"Francisca-{mes_abrev}-{data.year}-joinvix.pdf"
    for ano, mes in ((data.year, data.month), (data.year, data.month - 1 or 12)):
        url = f"https://revistafrancisca.com.br/wp-content/uploads/{ano}/{mes:02d}/{nome_arquivo}"
        r = sessao.get(url, timeout=120)
        if r.status_code == 200 and r.content[:4] == b"%PDF":
            salvar(destino, r.content)
            log(f"  -> {destino} ({len(r.content):,} bytes)")
            marcar_processado(estado, "revistafrancisca", info["edicao"])
            return True
    log("  ERRO: PDF nao encontrado em nenhuma pasta de upload candidata")
    return False


# --------------------------------------------------------------------------
# tribuna (blog do espeto) - PDF com hash aleatorio, precisa raspar sempre
# --------------------------------------------------------------------------
def achar_tribuna(sessao):
    url = "https://www.blogdoespeto.com/tribuna"
    r = sessao.get(url, timeout=30)
    r.raise_for_status()
    m = re.search(r'pdfUrl%22%3A%22(.+?)%22', r.text)
    if not m:
        return None
    return urllib.parse.unquote(m.group(1))


def baixar_tribuna(cfg, sessao, estado, so_verificar):
    j = cfg["jornais"]["tribuna"]
    url = achar_tribuna(sessao)
    if not url:
        log(f"{j['nome']}: nao encontrei o link do PDF na pagina")
        return False
    log(f"{j['nome']}: {url}")
    if so_verificar:
        return True

    # a pagina nao mostra data/numero de edicao - o hash no link e o unico
    # identificador estavel. Sem isso, toda vez que o arquivo "sai" da pasta
    # "jornais do interior" (ex.: apos montar a clipagem do dia) o script
    # rebaixava a mesma edicao com a data de hoje, criando uma copia nova por
    # dia mesmo sem nenhuma edicao nova ter saido - ja_processado evita isso.
    if ja_processado(estado, "tribuna", url):
        log("  edicao ja processada anteriormente, pulando")
        return True

    # so usa a data de hoje quando e de fato uma edicao nova (dia em que a
    # mudanca foi notada)
    destino = destino_pdf(cfg, "tribuna", datetime.now())
    if ja_existe(destino):
        log(f"  ja baixado ({destino.name}), pulando")
        marcar_processado(estado, "tribuna", url)
        return True

    r = sessao.get(url, timeout=120)
    r.raise_for_status()
    if r.content[:4] != b"%PDF":
        log("  ERRO: resposta nao parece PDF")
        return False

    salvar(destino, r.content)
    log(f"  -> {destino} ({len(r.content):,} bytes)")
    marcar_processado(estado, "tribuna", url)
    return True


# --------------------------------------------------------------------------
# voltagrande - viewer pubhtml5.com; config.js tem 'fliphtml5_pages' legivel
# (o 'bookConfig' do mesmo arquivo e ofuscado, mas essa chave nao)
# --------------------------------------------------------------------------
def achar_voltagrande(sessao):
    r = sessao.get("https://voltagrandeonline.com.br/conteudo-completo/", timeout=30)
    r.raise_for_status()
    m = re.search(
        r'href="(https://voltagrandeonline\.com\.br/conteudo-completo/\d+-vg-\d+/)"[^>]*>\s*VG\s*(\d+)',
        r.text,
    )
    if not m:
        # o link e o numero podem vir em blocos separados - tenta so o primeiro link do padrao
        m = re.search(r'href="(https://voltagrandeonline\.com\.br/conteudo-completo/(\d+)-vg-(\d+)/)"', r.text)
        if not m:
            return None
        url_edicao, _, numero = m.groups()
    else:
        url_edicao, numero = m.groups()

    r2 = sessao.get(url_edicao, timeout=30)
    r2.raise_for_status()
    m_data = re.search(r"VG\s*" + re.escape(numero) + r"\s*-\s*(\d{2}/\d{2}/\d{4})", r2.text)
    data = datetime.strptime(m_data.group(1), "%d/%m/%Y") if m_data else datetime.now()

    m_iframe = re.search(r'src="(https://online\.pubhtml5\.com/([a-z0-9]+)/([a-z0-9]+)/)"', r2.text)
    if not m_iframe:
        return None
    iframe_url, livro, codigo = m_iframe.groups()

    r3 = sessao.get(f"https://online.pubhtml5.com/{livro}/{codigo}/javascript/config.js", timeout=30)
    r3.raise_for_status()
    idx = r3.text.find('"fliphtml5_pages":')
    if idx == -1:
        return None
    start = r3.text.find("[", idx)
    depth, end = 0, None
    for i in range(start, len(r3.text)):
        if r3.text[i] == "[":
            depth += 1
        elif r3.text[i] == "]":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    paginas = json.loads(r3.text[start:end])
    hashes = [p["n"][0] for p in paginas]
    return {
        "edicao": numero, "data": data, "livro": livro, "codigo": codigo, "hashes": hashes,
    }


def baixar_voltagrande(cfg, sessao, estado, so_verificar):
    j = cfg["jornais"]["voltagrande"]
    info = achar_voltagrande(sessao)
    if not info:
        log(f"{j['nome']}: nao encontrei a edicao mais recente / config do viewer")
        return False
    log(f"{j['nome']}: VG {info['edicao']} ({info['data']:%d/%m/%Y}), {len(info['hashes'])} paginas")
    if so_verificar:
        return True

    if ja_processado(estado, "voltagrande", info["edicao"]):
        log("  edicao ja processada anteriormente, pulando")
        return True

    destino = destino_pdf(cfg, "voltagrande", info["data"])
    if ja_existe(destino):
        log(f"  ja baixado ({destino.name}), pulando")
        marcar_processado(estado, "voltagrande", info["edicao"])
        return True

    imagens = []
    base = f"https://online.pubhtml5.com/{info['livro']}/{info['codigo']}/files/large/"
    for i, h in enumerate(info["hashes"], start=1):
        r = sessao.get(base + h, timeout=60)
        if r.status_code != 200 or len(r.content) < 5_000:
            log(f"  pagina {i}: falhou, pulando")
            continue
        img = Image.open(io.BytesIO(r.content))
        if img.mode != "RGB":
            img = img.convert("RGB")
        imagens.append(img)
    if not imagens:
        log("  ERRO: nenhuma pagina baixada")
        return False

    destino.parent.mkdir(parents=True, exist_ok=True)
    imagens[0].save(destino, "PDF", save_all=True, append_images=imagens[1:], resolution=150.0)
    for img in imagens:
        img.close()
    log(f"  -> {destino} ({len(imagens)} paginas, {destino.stat().st_size:,} bytes)")
    marcar_processado(estado, "voltagrande", info["edicao"])
    return True


COLETORES = {
    "jcjoinville": baixar_jcjoinville,
    "folhadesbravador": baixar_folhadesbravador,
    "olider": baixar_olider,
    "hcnoticias": baixar_hcnoticias,
    "condominiosc": baixar_condominiosc,
    "revistafrancisca": baixar_revistafrancisca,
    "tribuna": baixar_tribuna,
    "voltagrande": baixar_voltagrande,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jornal", nargs="?", choices=list(COLETORES),
                    help="baixa so este jornal (padrao: todos)")
    ap.add_argument("--so-verificar", action="store_true",
                    help="so mostra a edicao mais recente, sem baixar")
    args = ap.parse_args()

    with CONFIG.open(encoding="utf-8") as fh:
        cfg = json.load(fh)

    sessao = requests.Session()
    sessao.headers.update(CABECALHOS)
    estado = carregar_estado()

    alvos = [args.jornal] if args.jornal else list(COLETORES)
    log(f"=== Jornais regionais ({len(alvos)}) ===")

    falhas = 0
    for chave in alvos:
        try:
            ok = COLETORES[chave](cfg, sessao, estado, args.so_verificar)
        except Exception as erro:
            log(f"{chave}: ERRO inesperado - {erro}")
            ok = False
        if not ok:
            falhas += 1

    if falhas:
        log(f"{falhas} de {len(alvos)} fonte(s) falharam.")
    return 1 if falhas == len(alvos) else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)

# Clipagem — Governo do Estado de Santa Catarina

Automação de download de jornais para montagem da clipagem diária.

## Estrutura

```
STUDIO/
  automacao/
    config.json              # cadastro dos jornais (fonte da verdade)
    Baixar Jornais.cmd       # atalho: roda todos os jornais ativos
    scripts/
      baixar_jornal.py       # baixa página por página e une num PDF
    logs/                    # um .log por dia
  JORNAIS/
    AAAA-MM-DD/             # uma pasta por dia, todos os jornais daquele dia juntos
```

## Como rodar

```bash
py automacao/scripts/baixar_jornal.py agazeta
```

Parâmetros: `--edicao N` força uma edição, `--so-verificar` só informa qual é a
mais recente, `--guardar-jpg` mantém também os JPGs soltos.

## Convenção de nomes

`AAAAMMDD_<id_veiculo>_<slug>.pdf` — ex.: `20260724_102_agazetasaobentodosul.pdf`

| Veículo | ID | Slug |
|---|---|---|
| A Gazeta — São Bento do Sul | 102 | `agazetasaobentodosul` |
| Correio do Povo — Jaraguá do Sul | 99 | `correiodopovojaraguadosul` |
| Diário do Iguaçu — Chapecó | 38 | `diariodoiguacuchapeco` |

## Regra de ouro

**Sempre confirmar que a edição é a mais recente** — em toda fonte, toda vez.
Nunca confiar em número de edição fixo nem em número informado de memória: subir
a numeração até dar 404, conferir `Last-Modified`, ler a data no índice. Em
24/07/2026 a edição pedida foi a 8981 quando a do dia já era a 8982.

**Nem confiar na posição na lista.** O índice do Diário do Iguaçu aparece em ordem
**crescente** (mais recente por último); o do Correio do Povo, decrescente. Extrair
a **data** de cada link e escolher a maior é o único critério que funciona nos dois.
Em edições agrupadas de fim de semana, usar a maior data do grupo — elas cruzam o
mês (`edicao-3107-e-01-e-02082026`).

## Situação das fontes

- **A Gazeta** — aberto, funcionando. URL por página:
  `agazetaonline.com.br/edicoes/{edicao}/pages/{pagina}.jpg`. O script descobre a
  edição mais recente sozinho subindo a partir de `edicao_semente` até dar 404
  três vezes seguidas — não depende de número fixo. Vale atualizar a semente de
  vez em quando para encurtar a varredura.
  **Correção em 21/09/2026**: passou a publicar também às segundas-feiras
  (edição 9.031 confirmada pela própria capa, "Segunda-feira, 21 de setembro de
  2026") — antes achava-se que não publicava. Não assumir mais isso; a regra de
  ouro (subir numeração / conferir `Last-Modified`) já pega isso sozinha, então
  não é preciso tratar ausência de edição de segunda como certeza.
- **Correio do Povo** — resolvido, mas em duas etapas. O **índice** de edições
  (`accounts.ocp.news/jornal-digital`) exige sessão logada; o **PDF** em
  `/storage/newspapers/pdf/{hash}.pdf` é público, baixa sem cookie nenhum. Cada
  edição já vem como um PDF único e pronto — não precisa montar página por página.
  Os ids de edição **não** acompanham a ordem das datas (16/07 = 9280, acima de
  17/07 = 9276), então é obrigatório ler o índice e casar data com link. Publica
  de terça a sábado; a clipagem cobre terça a sexta.
- **Navegador: usar o Chrome do usuário, não o interno.** As sessões de assinante
  ficam salvas no Chrome dele (MCP `claude-in-chrome`). O navegador embutido do
  Claude é um perfil separado e sempre aparece deslogado — foi o que fez o DI
  parecer bloqueado por dias. Antes de concluir que uma fonte exige login,
  tente pelo Chrome do usuário.
- **Diário do Iguaçu** — RESOLVIDO. Pelo Chrome do usuário a edição abre inteira.
  A página traz a **edição completa num PDF único** (link do dropdown,
  `/files/{id}/{hash}`, `application/pdf`) — não precisa montar página por página.
  Esse PDF é **público**: baixa sem cookie. O login serve só para ver o link.
  Mesmo padrão do Correio do Povo. Em 27/07/2026: PDF = 2843252, páginas soltas =
  2843253..2843276 (ids sequenciais, dentro de `g.magazine-page > image`).
- **Diário do Iguaçu (histórico)** — índice de edições é público
  (`/edicoes-online/diario-do-iguacu/edicao-{ddmmaaaa}`), mas as páginas são
  "Área exclusiva para Assinantes — DI PREMIUM". Páginas servidas como
  `/files/{id}/{hash}`, sem numeração previsível: exige raspar o DOM da edição.

- **DC, AN e Santa (NSC)** — RESOLVIDOS, e são os mais fáceis: **não precisam de
  navegador nem de login**. A edição inteira é um PDF público de nome previsível:
  `flip.nsctotal.com.br/wp-content/uploads/{ano}/{mes}/{arquivo}_{AAAAMMDD}_todas.pdf`
  com `arquivo` = `diariocatarinense`, `anoticia`, `jornaldesantacatarina`
  (atenção: **não** é `santa`). Rode `py automacao/scripts/baixar_nsc.py`.
  Duas pegadinhas: a pasta do mês é a do **upload**, não a da edição — a de
  01/08/2026 estava em `/2026/07/`, por isso o script tenta três meses. E o
  servidor responde **200 com 0 byte** para arquivo inexistente, então é preciso
  exigir `application/pdf` e tamanho mínimo antes de aceitar.
  O `ed_impressa_jn` do índice **não** entra na URL do PDF — pode ignorar.
- **ND Mais** — RESOLVIDO, é o mais trabalhoso. Sem PDF pronto: uma pasta por
  página (`up`, `up1`, … `up25`) e nome de arquivo em timestamp. As imagens **não
  estão todas no DOM renderizado** (carrega sob demanda) — extrair do
  `documentElement.outerHTML` por regex. Rode `py automacao/scripts/baixar_ndmais.py`.
  **Não é baixado de segunda a sexta** — só entra na rodada de sábado
  (`clipagem-sabado-4h`), junto com DC/AN/Santa.

## Velocidade — leia antes de sair abrindo o navegador

A ordem certa, do mais rápido ao mais lento:

1. **Sem navegador**: A Gazeta, DC, AN e Santa. São 4 dos 7, e resolvem em segundos.
2. **Navegador só para achar o link**: Diário do Iguaçu e Correio do Povo — o
   índice exige sessão, mas o PDF em si é público e baixa por PowerShell.
3. **Navegador o tempo todo**: só o ND Mais.

A partir de 11/09/2026, por pedido do usuário, a clipagem de segunda a sexta
(`clipagem-diaria-5h`) baixa SOMENTE A Gazeta. Diário do Iguaçu e Correio do Povo
ficaram fora dela (mesmo tendo caminho sem login, não são mais parte da rotina
diária automática).

Em 12/09/2026 a mesma restrição foi aplicada à tarefa de sábado
(`clipagem-sabado-4h`, reativada nesse dia): ela também baixa SOMENTE A Gazeta
(que publica terça a sábado, cobrindo o dia que a diária de seg-sex não pega).
DC, AN, Santa e ND Mais NÃO são mais baixados automaticamente por nenhuma tarefa
agendada — ficaram sem rotina até o usuário pedir de novo. A tarefa
`clipagem-jornais-sabado` (sexta 8h, pergunta se precisa baixar edições de fim
de semana) ficou sem função prática nesse novo desenho e segue desativada.

Em 24/09/2026 o usuário cancelou a rotina de recorte das colunas de opinião
(Paulo Rolemberg e Raul Sartori) que rodava dentro da `clipagem-diaria-5h`.
Não recorte nem envie imagens de página/coluna nessa tarefa.

## Download de A Gazeta migrou para a nuvem (24/09/2026)

A tarefa local `clipagem-diaria-5h` nunca disparava de fato às 23h30: o PC do
usuário fica desligado à noite, então a execução só acontecia quando ele ligava
a máquina de manhã (~5h-6h40), um catch-up, não o agendamento real. Como a
regra de ouro (confirmar a edição mais recente) é sensível a horário — A Gazeta
publica a edição do dia seguinte à noite — isso importava.

Solução: o download em si agora roda numa **rotina em nuvem** (Claude Code
routine, não depende do PC do usuário estar ligado), às 23h30 horário de
Brasília. Peças:
- Repositório Git: https://github.com/juosoriom-gif/studio-clipagem (privado).
  Contém só `automacao/` (scripts + config.json) e `CLAUDE.md` — a pasta
  `JORNAIS/` e outros arquivos da raiz da STUDIO ficam de fora (`.gitignore`),
  não fazem parte do repositório.
- Rotina: "Clipagem - A Gazeta 23h30"
  (https://claude.ai/code/routines/trig_01Xckp4oMs3xMwTso7AREdf8), cron
  `30 2 * * *` (UTC) = 23h30 America/Sao_Paulo. Roda
  `TZ=America/Sao_Paulo python3 automacao/scripts/baixar_jornal.py agazeta`
  (fixar TZ é necessário — o script decide a data da edição pela hora local,
  e o container da nuvem roda em UTC por padrão), valida o PDF com pypdf,
  copia o resultado para `entregas/AAAA-MM-DD/` no repositório, atualiza
  `edicao_semente` no `config.json` e dá commit+push.
- `automacao/config.json`: `pasta_saida` e `pasta_saida_interior` viraram
  caminhos **relativos** (`JORNAIS`, não `C:\Users\...`) para funcionar tanto
  local quanto no container Linux da nuvem — os scripts sempre são chamados
  com cwd na raiz da STUDIO, então isso não muda o comportamento local.
- A tarefa local `clipagem-diaria-5h` mudou de função: não baixa mais nada,
  só dá `git pull` no repositório e copia o que estiver em `entregas/` para
  `JORNAIS/` (mesma convenção de nome de pasta/arquivo). Ver o SKILL.md da
  tarefa para os passos exatos.

Se o usuário disser que o PDF não apareceu em `JORNAIS/`, a nuvem pode ter
rodado (ela não depende do PC) — antes de reinvestigar a fonte, cheque
`git log`/`entregas/` no repositório e rode `git pull` local antes de
suspeitar de bug na automação de download em si.

Não investigue de novo o que já está escrito aqui. Em 01/08/2026 a rodada
completa levou 45 minutos porque foi tudo redescoberto do zero; com este
documento, os 4 primeiros saem sem abrir o Chrome.

## Ao adicionar um jornal novo

Cadastre em `config.json`. Se as páginas seguirem um padrão de URL numerada,
basta `tipo: "paginas_jpg"` + `url_modelo` com `{edicao}` e `{pagina}` — o script
existente já dá conta. Padrões diferentes precisam de um coletor próprio.

## Detalhes que já custaram tempo

- O servidor da Gazeta devolve 403 sem `User-Agent` de navegador.
- Placeholders vêm com menos de 10 KB; por isso o script exige tamanho mínimo
  antes de aceitar uma página como válida.
- Pillow não grava PDF a partir de imagem com canal alpha — converter para RGB.
- **A Gazeta publica a edição de amanhã hoje à noite** (~20h30–23h30, ver
  [[clipagem-agazeta-horario-publicacao]] na memória). Por isso `baixar_jornal.py`
  usa a hora de execução para decidir a data da edição: rodando de madrugada
  (ex.: 5h) a edição mais recente já é a de hoje; rodando à noite (ex.: 23h30) a
  edição mais recente ainda é a de amanhã — o script soma 1 dia quando roda a
  partir das 12h. Corrigido em 21/09/2026 quando a tarefa `clipagem-diaria-5h`
  passou a rodar às 23h30 em vez de 5h.
